"""Provider interface. A provider turns text into JSON matching a schema; it never sees DEM data
beyond the structured facts it is given, and its output is always validated by the caller."""
from __future__ import annotations

from dataclasses import dataclass, field


class ProviderError(Exception):
    """The provider failed (network, quota, refusal, malformed output)."""

    def __init__(self, message: str, code: str = "AI_PROVIDER_ERROR"):
        super().__init__(message)
        self.code = code


class ProviderUnavailable(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, "AI_UNAVAILABLE")


@dataclass
class ProviderResult:
    data: dict
    provider: str
    model: str
    model_version: str = ""
    raw_text: str = ""
    meta: dict = field(default_factory=dict)


class AIProvider:
    name = "base"
    #: True for language models; False for the deterministic rule parser.
    is_language_model = True

    def describe(self) -> dict:
        return {"provider": self.name, "model": getattr(self, "model", ""), "is_language_model": self.is_language_model}

    def available(self) -> tuple[bool, str]:
        return True, ""

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> ProviderResult:
        """Return JSON for ``task`` ("interpret" | "explain") matching ``schema``."""
        raise NotImplementedError
