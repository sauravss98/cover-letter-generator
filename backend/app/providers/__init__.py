from .anthropic_provider import AnthropicProvider
from .base import Provider, ProviderError
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

# Registry keyed by the id the frontend sends. Add a provider by implementing
# the `Provider` protocol and registering it here.
PROVIDERS: dict[str, Provider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
}

__all__ = ["PROVIDERS", "Provider", "ProviderError"]
