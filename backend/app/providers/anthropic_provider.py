import base64

import anthropic

from ..extract import SourceDoc
from .base import (
    MAX_RETRIES,
    REQUEST_TIMEOUT_S,
    SYSTEM_PROMPT,
    TASK_PROMPT,
    ProviderError,
    require_text,
    sdk_error_message,
    status_error,
    timeout_error,
    wrap,
)


_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


def _block(doc: SourceDoc) -> dict:
    # Claude reads PDFs natively (layout, tables, scanned pages), so send the original.
    if doc.pdf_bytes is not None:
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(doc.pdf_bytes).decode("ascii"),
            },
            "title": doc.title,
        }
    return {"type": "text", "text": wrap(doc)}


class AnthropicProvider:
    name = "Claude"
    default_model = "claude-opus-5-5"
    env_key = "ANTHROPIC_API_KEY"

    def generate(self, docs, instructions, api_key, model):
        content = [_block(d) for d in docs] + [{"type": "text", "text": TASK_PROMPT}]
        if instructions and instructions.strip():
            content.append(
                {"type": "text", "text": f"Additional instructions from the applicant:\n{instructions.strip()}"}
            )

        client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_S, max_retries=MAX_RETRIES)
        params = dict(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        try:
            if model in _FALLBACK_MODELS:
                # On a safety-classifier refusal, let the API retry on its recommended fallback model.
                response = client.beta.messages.create(
                    **params,
                    output_config={"effort": "medium"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
            else:
                # User-chosen older model: send a plain request, since effort/fallbacks may be rejected.
                response = client.messages.create(**params)
        except anthropic.APIStatusError as e:
            raise status_error(e.status_code, self.name, sdk_error_message(e))
        except anthropic.APITimeoutError:
            raise timeout_error(self.name)
        except anthropic.APIConnectionError:
            raise ProviderError(502, "Could not reach the Claude API.")

        if response.stop_reason == "refusal":
            raise ProviderError(422, "Claude declined to write this cover letter.")
        return require_text("".join(b.text for b in response.content if b.type == "text"))
