import openai

from .base import SYSTEM_PROMPT, ProviderError, require_text, status_error, user_prompt


class OpenAIProvider:
    name = "OpenAI"
    default_model = "gpt-6.1-sol"
    env_key = "OPENAI_API_KEY"

    def generate(self, docs, instructions, api_key, model):
        client = openai.OpenAI(api_key=api_key)
        try:
            response = client.responses.create(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=user_prompt(docs, instructions),
                max_output_tokens=16000,
            )
        except openai.APIStatusError as e:
            raise status_error(e.status_code, self.name, e.message)
        except openai.APIConnectionError:
            raise ProviderError(502, "Could not reach the OpenAI API.")
        return require_text(response.output_text)
