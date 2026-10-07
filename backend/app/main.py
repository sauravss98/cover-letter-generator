import logging
import os
import re
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

load_dotenv()

from . import export  # noqa: E402
from .extract import MAX_DOC_CHARS, MAX_UPLOAD_BYTES, UnsupportedFileError, from_text, from_upload  # noqa: E402
from .providers import PROVIDERS, ProviderError  # noqa: E402
from .providers.base import split_metadata  # noqa: E402

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Cover Letter Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_REQUEST_BYTES = 25 * 1024 * 1024  # two 10 MB uploads plus form fields
MAX_EXPORT_CHARS = 20_000
MAX_INSTRUCTIONS_CHARS = 2_000
# Model ids are interpolated into provider URLs (e.g. Gemini's /models/{model}:generateContent),
# so restrict them to a safe character set.
MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    # Reject oversized bodies before multipart parsing spools them to disk. Requests without
    # Content-Length (chunked) aren't covered; put a reverse proxy body limit in front in production.
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request is too large."})
    return await call_next(request)


async def _read_upload(f: UploadFile) -> bytes:
    # Read at most one byte past the limit so an oversized file can't be pulled fully into memory.
    return await f.read(MAX_UPLOAD_BYTES + 1)


class ProviderInfo(BaseModel):
    id: str
    name: str
    default_model: str
    server_key_available: bool  # True if the server has its own key, so the user may leave theirs blank


class GenerateResponse(BaseModel):
    cover_letter: str
    company: str  # extracted from the job description; "" if unknown
    role: str
    provider: str
    model: str


class ExportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_EXPORT_CHARS)
    format: Literal["pdf", "docx"]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/providers", response_model=list[ProviderInfo])
def list_providers():
    return [
        ProviderInfo(
            id=pid,
            name=p.name,
            default_model=p.default_model,
            server_key_available=bool(os.getenv(p.env_key)),
        )
        for pid, p in PROVIDERS.items()
    ]


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    resume: UploadFile = File(...),
    jd_file: UploadFile | None = File(None),
    jd_text: str | None = Form(None, max_length=MAX_DOC_CHARS),
    instructions: str | None = Form(None, max_length=MAX_INSTRUCTIONS_CHARS),
    provider: str = Form("anthropic", max_length=32),
    api_key: str | None = Form(None, max_length=512),
    model: str | None = Form(None, max_length=100),
):
    impl = PROVIDERS.get(provider)
    if impl is None:
        raise HTTPException(status_code=400, detail="Unknown provider.")
    model_id = (model or "").strip() or impl.default_model
    if not re.fullmatch(MODEL_PATTERN, model_id):
        raise HTTPException(status_code=400, detail="Invalid model name.")

    # The user's own key wins; otherwise fall back to the server's key, if configured.
    key = (api_key or "").strip() or os.getenv(impl.env_key)
    if not key:
        raise HTTPException(status_code=400, detail=f"Enter your {impl.name} API key.")

    try:
        docs = [from_upload(resume.filename, await _read_upload(resume), "resume")]
        if jd_file is not None and jd_file.filename:
            docs.append(from_upload(jd_file.filename, await _read_upload(jd_file), "job_description"))
        elif jd_text and jd_text.strip():
            docs.append(from_text(jd_text, "job_description"))
        else:
            raise UnsupportedFileError("Provide a job description as a file or text.")
    except UnsupportedFileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # Provider SDK calls block; run them off the event loop so one slow request
        # does not freeze the whole server.
        raw = await run_in_threadpool(impl.generate, docs, instructions, key, model_id)
    except ProviderError as e:
        # Never log the API key; provider/model/message are enough to debug.
        logger.warning("Provider error [%s %s] %s: %s", provider, model_id, e.status_code, e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)

    result = split_metadata(raw)
    if not result.letter:
        raise HTTPException(status_code=502, detail="The model returned an empty letter. Try again.")
    return GenerateResponse(
        cover_letter=result.letter, company=result.company, role=result.role, provider=provider, model=model_id
    )


@app.post("/api/export")
def export_letter(req: ExportRequest):
    if req.format == "pdf":
        data, media = export.to_pdf(req.text), "application/pdf"
    else:
        data = export.to_docx(req.text)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="cover_letter.{req.format}"'},
    )
