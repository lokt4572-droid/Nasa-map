"""AI provider selection. Configured on the backend only (settings / environment):

AI_PROVIDER = "rules" (default; deterministic parser, no model) | "ollama" (local, free) |
              "anthropic" (remote; ANTHROPIC_API_KEY in the backend environment) | "none"
"""
from __future__ import annotations

from django.conf import settings

from .base import AIProvider, ProviderUnavailable


def get_provider() -> AIProvider | None:
    name = (getattr(settings, "AI_PROVIDER", "rules") or "none").lower()
    if name == "none":
        return None
    if name == "rules":
        from .local_provider import RulesProvider

        return RulesProvider()
    if name == "ollama":
        from .local_provider import OllamaProvider

        return OllamaProvider()
    if name == "anthropic":
        from .remote_provider import AnthropicProvider

        return AnthropicProvider()
    raise ProviderUnavailable(f"Unknown AI_PROVIDER {name!r}")


__all__ = ["AIProvider", "ProviderUnavailable", "get_provider"]
