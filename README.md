# Cover Letter Generator

Upload a resume and a job description and get back a tailored cover letter. You can edit it, then download it as PDF or Word.

Works with **Claude**, **OpenAI** or **Gemini**. Each user chooses a provider and enters their own API key in the UI.

> **API keys and subscriptions:** a chat subscription (Claude Pro/Max, ChatGPT Plus, Gemini Advanced) is not an API key and cannot be used here. Create an API key instead:
> [Anthropic Console](https://console.anthropic.com/settings/keys) · [OpenAI Platform](https://platform.openai.com/api-keys) · [Google AI Studio](https://aistudio.google.com/apikey)

## Run it

**Backend** (Python 3.10+), from `backend/`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # optional: add server-side default keys
uvicorn app.main:app --reload --timeout-graceful-shutdown 5 --port 8000
```

**Frontend** (Node 20+), from `frontend/`:

```powershell
npm install
npm run dev
```

Open http://localhost:5173.

## How keys are handled

- The browser sends the key with each request. The backend uses it for that one call and never stores it.
- "Remember key in this browser" saves it in the browser's `localStorage` on your machine only.
- If `backend/.env` sets a provider's key, that key is used whenever the user leaves the field blank. Leave it unset if you host this for other people and don't want them using your key.

## Before hosting it publicly

The app is safe to run locally as is. If you deploy it for other people:

- **Serve it over HTTPS only.** Users' API keys travel in each request.
- **Leave the server keys in `.env` empty** unless you want strangers spending your API credit. Anyone who can reach the site can use a key configured there.
- **Put a reverse proxy in front** (nginx, Caddy, or your platform's equivalent) to cap the request body size (around 25 MB) and add rate limiting. The app rejects oversized requests that declare their size, but requests sent without a declared size (chunked) still need the proxy's limit.
- **Set `CORS_ORIGINS`** to your real frontend URL.

Built-in limits: 10 MB per upload, 30 PDF pages, 100k characters of text per document, 2k characters of extra instructions, 20k characters for export, and a DOCX zip-bomb check. Model names are restricted to a safe character set.
