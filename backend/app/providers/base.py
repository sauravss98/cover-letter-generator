from typing import Protocol

from ..extract import SourceDoc

SYSTEM_PROMPT = """You write cover letters for job applicants.

You will receive the applicant's resume and a job description. Write a cover letter that:
- Is addressed to the hiring manager (use a name only if the job description gives one).
- Connects the applicant's real experience to the specific requirements of the role, with concrete examples and numbers taken from the resume.
- Never invents experience, skills, employers, or credentials that are not in the resume.
- Is around 250-400 words, in 3-5 paragraphs, professional and specific rather than generic.
- Ends with a sign-off using the applicant's name from the resume.

Output only the letter text, starting with the salutation. No subject line, no date or address block, no markdown, no commentary before or after."""

TASK_PROMPT = "Write the cover letter for this applicant and job."

# Per-attempt timeout for provider calls. SDK retries are capped at 1, so worst case is ~2x this.
REQUEST_TIMEOUT_S = 120
MAX_RETRIES = 1


def timeout_error(provider: str) -> "ProviderError":
    return ProviderError(504, f"{provider} took too long to respond. Try again, or pick a faster model.")


def sdk_error_message(e: Exception) -> str:
    """Pull the human-readable message out of an Anthropic/OpenAI SDK error body."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if body.get("message"):
            return str(body["message"])
    return getattr(e, "message", "") or str(e)


class ProviderError(RuntimeError):
    """A provider failure normalised to an HTTP status the API layer can return."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class Provider(Protocol):
    name: str
    default_model: str
    env_key: str  # env var holding the server-side fallback API key

    def generate(
        self,
        docs: list[SourceDoc],
        instructions: str | None,
        api_key: str,
        model: str,
    ) -> str: ...


def wrap(doc: SourceDoc) -> str:
    return f"<{doc.title}>\n{doc.text}\n</{doc.title}>"


def user_prompt(docs: list[SourceDoc], instructions: str | None) -> str:
    """Single text prompt for providers that receive documents as text."""
    parts = [wrap(d) for d in docs] + [TASK_PROMPT]
    if instructions and instructions.strip():
        parts.append(f"Additional instructions from the applicant:\n{instructions.strip()}")
    return "\n\n".join(parts)


def require_text(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        raise ProviderError(502, "The model returned an empty response.")
    return text


def status_error(status: int | None, provider: str, detail: str = "") -> ProviderError:
    """Map an upstream HTTP status to the error we surface to the client."""
    suffix = f": {detail}" if detail else ""
    if status in (401, 403):
        return ProviderError(401, f"{provider} rejected the API key{suffix}")
    if status == 404:
        return ProviderError(400, f"{provider} model not found — check the model name{suffix}")
    if status == 429:
        return ProviderError(429, f"{provider} rate limit or quota exceeded. Try again shortly.")
    if status is not None and 400 <= status < 500:
        return ProviderError(400, f"{provider} rejected the request{suffix}")
    return ProviderError(502, f"{provider} is unavailable ({status or 'no status'}){suffix}. Try again later.")
