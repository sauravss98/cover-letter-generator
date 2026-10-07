from google import genai
from google.genai import errors, types

from .base import SYSTEM_PROMPT, ProviderError, require_text, status_error, user_prompt


class GeminiProvider:
    name = "Gemini"
    default_model = "gemini-3.8-flash"
    env_key = "GEMINI_API_KEY"

    def generate(self, docs, instructions, api_key, model):
        client = genai.Client(api_key=api_key)
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
            raise status_error(code, self.name, e.message or "")
        except Exception as e:  # network errors surface as httpx exceptions
            raise ProviderError(502, f"Could not reach the Gemini API ({type(e).__name__}).")
        return require_text(response.text)
