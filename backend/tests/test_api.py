import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import main
from app.providers import ProviderError

client = TestClient(main.app)

LETTER = "Dear Hiring Manager,\n\nI am excited — truly — to apply.\n\nSincerely,\nAda Lovelace"


class FakeProvider:
    name = "Fake"
    default_model = "fake-1"
    env_key = "FAKE_API_KEY"

    def __init__(self, error: ProviderError | None = None):
        self.error = error
        self.calls = []

    def generate(self, docs, instructions, api_key, model):
        self.calls.append((docs, instructions, api_key, model))
        if self.error:
            raise self.error
        return LETTER


@pytest.fixture
def fake(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setitem(main.PROVIDERS, "fake", provider)
    monkeypatch.delenv("FAKE_API_KEY", raising=False)
    return provider


def _docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_providers_lists_all():
    ids = {p["id"] for p in client.get("/api/providers").json()}
    assert {"anthropic", "openai", "gemini"} <= ids


def test_generate_with_docx_resume_and_text_jd(fake):
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.docx", _docx_bytes("Ada Lovelace", "Analyst"), "application/octet-stream")},
        data={"jd_text": "Senior engineer", "provider": "fake", "api_key": "user-key"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"cover_letter": LETTER, "company": "", "role": "", "provider": "fake", "model": "fake-1"}
    docs, _, key, model = fake.calls[0]
    assert [d.title for d in docs] == ["resume", "job_description"]
    assert "Ada Lovelace" in docs[0].text
    assert key == "user-key" and model == "fake-1"


def test_generate_uses_server_key_when_user_key_blank(fake, monkeypatch):
    monkeypatch.setenv("FAKE_API_KEY", "server-key")
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"jd_text": "Role", "provider": "fake", "model": "fake-2"},
    )
    assert r.status_code == 200, r.text
    assert fake.calls[0][2:] == ("server-key", "fake-2")


def test_generate_requires_key(fake):
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"jd_text": "Role", "provider": "fake"},
    )
    assert r.status_code == 400
    assert "API key" in r.json()["detail"]


def test_generate_requires_jd(fake):
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"provider": "fake", "api_key": "k"},
    )
    assert r.status_code == 400


def test_generate_rejects_unsupported_file(fake):
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.png", b"\x89PNG", "image/png")},
        data={"jd_text": "Role", "provider": "fake", "api_key": "k"},
    )
    assert r.status_code == 400
    assert "unsupported" in r.json()["detail"]


def test_generate_unknown_provider():
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"jd_text": "Role", "provider": "nope", "api_key": "k"},
    )
    assert r.status_code == 400


def test_provider_error_is_propagated(monkeypatch):
    monkeypatch.setitem(main.PROVIDERS, "fake", FakeProvider(ProviderError(401, "bad key")))
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"jd_text": "Role", "provider": "fake", "api_key": "k"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "bad key"


def test_export_pdf_contains_text():
    r = client.post("/api/export", json={"text": LETTER, "format": "pdf"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Ada Lovelace" in text and "Dear Hiring Manager" in text


def test_export_docx_keeps_paragraphs():
    r = client.post("/api/export", json={"text": LETTER, "format": "docx"})
    assert r.status_code == 200
    paras = [p.text for p in Document(io.BytesIO(r.content)).paragraphs]
    assert paras[0] == "Dear Hiring Manager,"
    assert paras[-1] == "Sincerely,\nAda Lovelace"


def test_export_pdf_escapes_markup():
    r = client.post("/api/export", json={"text": "A <b> & C", "format": "pdf"})
    assert r.status_code == 200


# --- security limits ---

def _post(fake_files, data):
    return client.post("/api/generate", files=fake_files, data={"provider": "fake", "api_key": "k", **data})


def test_rejects_oversized_upload(fake):
    big = b"a" * (10 * 1024 * 1024 + 1)
    r = _post({"resume": ("cv.txt", big, "text/plain")}, {"jd_text": "Role"})
    assert r.status_code == 400
    assert "10 MB" in r.json()["detail"]


def test_rejects_too_long_extracted_text(fake):
    r = _post({"resume": ("cv.txt", b"a" * 100_001, "text/plain")}, {"jd_text": "Role"})
    assert r.status_code == 400
    assert "too long" in r.json()["detail"]


def test_rejects_docx_zip_bomb(fake):
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", b"\0" * (60 * 1024 * 1024))
    r = _post({"resume": ("cv.docx", buf.getvalue(), "application/octet-stream")}, {"jd_text": "Role"})
    assert r.status_code == 400
    assert not fake.calls


def test_corrupt_files_return_400_not_500(fake):
    for name in ("cv.pdf", "cv.docx"):
        r = _post({"resume": (name, b"not really a document", "application/octet-stream")}, {"jd_text": "Role"})
        assert r.status_code == 400, name


@pytest.mark.parametrize("model", ["../../v1/files", "gemini/../x", "a b", "-flag", "x" * 101])
def test_rejects_unsafe_model_names(fake, model):
    r = _post({"resume": ("cv.txt", b"Ada", "text/plain")}, {"jd_text": "Role", "model": model})
    assert r.status_code in (400, 422)
    assert not fake.calls


def test_rejects_long_instructions(fake):
    r = _post({"resume": ("cv.txt", b"Ada", "text/plain")}, {"jd_text": "Role", "instructions": "x" * 2001})
    assert r.status_code == 422


def test_rejects_huge_export():
    r = client.post("/api/export", json={"text": "x" * 20_001, "format": "pdf"})
    assert r.status_code == 422


def test_rejects_oversized_request_by_content_length():
    r = client.post("/api/generate", content=b"x", headers={"content-length": str(26 * 1024 * 1024)})
    assert r.status_code == 413


# --- responsiveness ---

@pytest.mark.anyio
async def test_slow_provider_does_not_block_other_requests(monkeypatch):
    import time

    import anyio
    import httpx

    class SlowProvider(FakeProvider):
        def generate(self, *args):
            time.sleep(1.5)  # blocking, like a real SDK call
            return LETTER

    monkeypatch.setitem(main.PROVIDERS, "slow", SlowProvider())
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        health_latency = None

        async def slow_generate():
            r = await ac.post(
                "/api/generate",
                files={"resume": ("cv.txt", b"Ada", "text/plain")},
                data={"jd_text": "Role", "provider": "slow", "api_key": "k"},
            )
            assert r.status_code == 200

        async def health():
            nonlocal health_latency
            await anyio.sleep(0.2)  # let generate start first
            start = time.monotonic()
            r = await ac.get("/api/health")
            health_latency = time.monotonic() - start
            assert r.status_code == 200

        async with anyio.create_task_group() as tg:
            tg.start_soon(slow_generate)
            tg.start_soon(health)

    assert health_latency < 0.5


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_sdk_error_message_extracts_human_text():
    from app.providers.base import sdk_error_message

    class E(Exception):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low."}}
        message = "Error code: 400 - {...}"

    assert sdk_error_message(E()) == "Your credit balance is too low."


# --- company / role metadata ---

def test_generate_returns_company_and_role(monkeypatch):
    class MetaProvider(FakeProvider):
        def generate(self, *args):
            return '{"company": "Acme Corp", "role": "Senior Engineer"}\n\n' + LETTER

    monkeypatch.setitem(main.PROVIDERS, "meta", MetaProvider())
    r = client.post(
        "/api/generate",
        files={"resume": ("cv.txt", b"Ada", "text/plain")},
        data={"jd_text": "Role", "provider": "meta", "api_key": "k"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["company"], body["role"], body["cover_letter"]) == ("Acme Corp", "Senior Engineer", LETTER)


@pytest.mark.parametrize(
    "raw, company, role",
    [
        ('{"company": "Acme", "role": "Dev"}\n\nDear X,', "Acme", "Dev"),
        ('```json\n{"company": "Acme", "role": "Dev"}\n```\n\nDear X,', "Acme", "Dev"),
        ('  {"company": "", "role": "Dev"}\nDear X,', "", "Dev"),
        ('{"company": 5, "role": null}\n\nDear X,', "", ""),
    ],
)
def test_split_metadata_parses_header(raw, company, role):
    from app.providers.base import split_metadata

    res = split_metadata(raw)
    assert (res.company, res.role, res.letter) == (company, role, "Dear X,")


@pytest.mark.parametrize("raw", ["Dear X,\n\nBody", "{not json}\n\nDear X,", "{curly opener in letter}"])
def test_split_metadata_falls_back_to_whole_text(raw):
    from app.providers.base import split_metadata

    res = split_metadata(raw)
    assert res.letter == raw.strip() and res.company == "" and res.role == ""
