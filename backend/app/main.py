import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

load_dotenv()

from . import export  # noqa: E402
from .extract import UnsupportedFileError, from_text, from_upload  # noqa: E402
from .providers import PROVIDERS, ProviderError  # noqa: E402

app = FastAPI(title="Cover Letter Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProviderInfo(BaseModel):
    id: str
    name: str
    default_model: str
    server_key_available: bool  # True if the server has its own key, so the user may leave theirs blank


class GenerateResponse(BaseModel):
    cover_letter: str
    provider: str
    model: str


class ExportRequest(BaseModel):
    text: str = Field(min_length=1)
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
    jd_text: str | None = Form(None),
    instructions: str | None = Form(None),
    provider: str = Form("anthropic"),
    api_key: str | None = Form(None),
    model: str | None = Form(None),
):
    impl = PROVIDERS.get(provider)
    if impl is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")

    # The user's own key wins; otherwise fall back to the server's key, if configured.
    key = (api_key or "").strip() or os.getenv(impl.env_key)
    if not key:
        raise HTTPException(status_code=400, detail=f"Enter your {impl.name} API key.")

    try:
        docs = [from_upload(resume.filename, await resume.read(), "resume")]
        if jd_file is not None and jd_file.filename:
            docs.append(from_upload(jd_file.filename, await jd_file.read(), "job_description"))
        elif jd_text and jd_text.strip():
            docs.append(from_text(jd_text, "job_description"))
        else:
            raise UnsupportedFileError("Provide a job description as a file or text.")
    except UnsupportedFileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model_id = (model or "").strip() or impl.default_model
    try:
        letter = impl.generate(docs, instructions, key, model_id)
    except ProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return GenerateResponse(cover_letter=letter, provider=provider, model=model_id)


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
