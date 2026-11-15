"""Remote provider: Claude through the official Anthropic Python SDK (optional dependency,
``pip install -r requirements-ai.txt``). The API key is read by the SDK from the BACKEND
environment (ANTHROPIC_API_KEY); it is never sent to the browser.

Requests use structured outputs (``output_config.format``) so the reply is JSON for the given
schema, and server-side refusal fallback (``fallbacks: "default"``) so a policy decline is
retried on Anthropic's recommended fallback model instead of failing outright."""
from __future__ import annotations

import json

from django.conf import settings

from .base import AIProvider, ProviderError, ProviderResult, ProviderUnavailable

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self):
        self.model = getattr(settings, "AI_MODEL", "") or DEFAULT_MODEL
        self.effort = getattr(settings, "AI_EFFORT", "") or "medium"
        self.timeout = float(getattr(settings, "AI_TIMEOUT_S", 60))
        self._client = None

    def _sdk(self):
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailable("The anthropic package is not installed (pip install -r requirements-ai.txt)") from exc
        return anthropic

    def client(self):
        if self._client is None:
            anthropic = self._sdk()
            self._client = anthropic.Anthropic(timeout=self.timeout, max_retries=2)
        return self._client

    def available(self) -> tuple[bool, str]:
        import os

        try:
            self._sdk()
        except ProviderUnavailable as exc:
            return False, str(exc)
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False, "No Anthropic credential in the backend environment (ANTHROPIC_API_KEY)"
        return True, ""

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> ProviderResult:
        anthropic = self._sdk()
        try:
            response = self.client().beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderUnavailable("The Anthropic credential was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Anthropic rate limit reached; try again later", "AI_RATE_LIMITED") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Anthropic API error (HTTP {exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Anthropic API not reachable") from exc
        if response.stop_reason == "refusal":
            raise ProviderError("The model declined the request", "AI_REFUSED")
        if response.stop_reason == "max_tokens":
            raise ProviderError("The model output was cut off", "AI_INVALID_OUTPUT")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("The model did not return valid JSON", "AI_INVALID_OUTPUT") from exc
        return ProviderResult(data, self.name, self.model, str(getattr(response, "model", "")), raw_text=text,
                              meta={"stop_reason": response.stop_reason})
