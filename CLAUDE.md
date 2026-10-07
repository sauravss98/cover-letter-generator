# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cover letter generator. FastAPI backend (`backend/`) and React + Vite + TypeScript frontend (`frontend/`). The user uploads a resume and a job description (file or pasted text), picks an LLM provider (Claude / OpenAI / Gemini), and supplies their own API key. The backend returns the letter text. The user edits it in the browser, then exports it to PDF or DOCX.

## Commands

Backend (run from `backend/`; the venv lives at `backend/.venv`):

```bash
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
.venv/Scripts/python -m pytest -q                                                       # all tests
.venv/Scripts/python -m pytest tests/test_api.py::test_export_docx_keeps_paragraphs -q  # single test
```

Frontend (run from `frontend/`):

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api -> localhost:8000 (vite.config.ts)
npm run build   # tsc type-check + production build; this is the frontend's only lint/check step
```

There is no frontend test suite. Backend tests never call real LLM APIs: they register a `FakeProvider` in `main.PROVIDERS` via monkeypatch.

## Architecture

**Request flow:** `POST /api/generate` (multipart) → `extract.py` turns each upload into a `SourceDoc` → `PROVIDERS[provider].generate(docs, instructions, api_key, model)` → plain letter text. Export is a separate stateless call, `POST /api/export {text, format}` → `export.py`. Because of that, user edits in the browser are what get exported, and the backend keeps no state.

**Provider abstraction (`app/providers/`):**
- `base.py` holds the shared `SYSTEM_PROMPT`, the `Provider` protocol, prompt helpers, and `ProviderError(status_code, message)`.
- Every provider must catch its own SDK's exceptions and re-raise `ProviderError`, usually via `status_error()`. `main.py` only knows about `ProviderError`. Never let SDK exceptions escape a provider.
- To add a provider: implement `name` / `default_model` / `env_key` / `generate()` and register it in `providers/__init__.py`. `GET /api/providers` and the frontend dropdown pick it up automatically. Also add its key URL to `KEY_HELP` in `frontend/src/App.tsx`.
- `SourceDoc` always has `.text`. For PDFs it also keeps `.pdf_bytes`. The Claude provider sends PDFs natively as `document` blocks; OpenAI and Gemini get the locally extracted text inside `<resume>` / `<job_description>` tags. A scanned PDF with no text layer is therefore accepted, but only Claude can read it.
- The Claude provider sends `output_config.effort`, `fallbacks: "default"`, and the `server-side-fallback-2026-07-01` beta only for the models in `_FALLBACK_MODELS`. Other user-chosen Claude models get a plain `messages.create`, because those params may be rejected.

**API keys:** the user's key comes in as a form field on each request and is never stored server-side. If the field is blank, the backend falls back to the env var named by the provider's `env_key` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` in `backend/.env`). `server_key_available` tells the UI whether the key field is optional. The frontend saves keys in `localStorage` only when "remember" is checked.

**Export details:** paragraphs are split on blank lines, and single newlines become line breaks (the sign-off block depends on this). The PDF uses ReportLab's built-in Helvetica, which covers cp1252 (smart quotes, em dashes) but not arbitrary Unicode. Paragraph text is XML-escaped, because ReportLab `Paragraph` parses markup.

## Notes

- Installed SDK majors are new: `anthropic` 1.x, `openai` 3.x (uses the Responses API), `google-genai` 2.x. Check signatures against the installed package rather than older examples.
- Default model IDs live on each provider class (`default_model`). Users can override the model per request in the UI.
