import httpx
from google import genai
from google.genai import errors, types

from .base import (
    REQUEST_TIMEOUT_S,
    SYSTEM_PROMPT,
    ProviderError,
    require_text,
    status_error,
    timeout_error,
    user_prompt,
)


class GeminiProvider:
    name = "Gemini"
    default_model = "gemini-3.6-flash"
    env_key = "GEMINI_API_KEY"

    def generate(self, docs, instructions, api_key, model):
        # The SDK has no default timeout; without one a stalled request hangs forever.
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_S * 1000,
                # Gemini often returns transient 503 "model overloaded"; retry with backoff.
                # 504 (deadline exceeded) is not retried: that attempt already used the full timeout.
                retry_options=types.HttpRetryOptions(
                    attempts=3, initial_delay=1.0, max_delay=8.0, http_status_codes=[500, 502, 503]
                ),
            ),
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_prompt(docs, instructions),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except errors.APIError as e:
            # Gemini reports an invalid key as 400 INVALID_ARGUMENT rather than 401.
            code = 401 if "API key" in (e.message or "") else e.code
            if code == 504:
                raise ProviderError(
                    504, f"Gemini model '{model}' did not respond in time. Try another model, e.g. {self.default_model}."
                )
            detail = e.message or e.status or ""
            if code == 503:
                detail = f"{detail} The model is overloaded; try again in a minute or use another model, e.g. {self.default_model}."
            raise status_error(code, self.name, detail.strip())
        except httpx.TimeoutException:
            raise timeout_error(self.name)
        except Exception as e:  # other network errors surface as httpx exceptions
            raise ProviderError(502, f"Could not reach the Gemini API ({type(e).__name__}).")
        return require_text(response.text)
