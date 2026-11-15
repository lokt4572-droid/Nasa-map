"""Local providers: a deterministic rule parser (always available, not a model) and Ollama
(a free, locally run model server)."""
from __future__ import annotations

import json
import re

from django.conf import settings

from .base import AIProvider, ProviderError, ProviderResult

_NUM = r"(\d+(?:\.\d+)?)"


class RulesProvider(AIProvider):
    """Keyword and number extraction with fixed rules. It is NOT an AI model; it exists so the
    assistant works without any model or key, and it is labelled as such in every response."""

    name = "rules"
    model = "rule-based-parser"
    model_version = "1"
    is_language_model = False

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> ProviderResult:
        if task == "interpret":
            return ProviderResult(self._interpret(user), self.name, self.model, self.model_version)
        if task == "explain":
            facts = json.loads(user)
            from apps.ai.services.route_assistant import template_explanation

            return ProviderResult(template_explanation(facts), self.name, self.model, self.model_version)
        raise ProviderError(f"Unsupported task {task!r}")

    @staticmethod
    def _interpret(text: str) -> dict:
        t = text.lower()
        out: dict = {
            "max_slope_deg": None, "allow_unknown_terrain": False, "avoid_known_hazards": True,
            "prefer_lower_roughness": False, "require_return_route": False, "hazard_buffer_m": None,
            "max_roughness_m": None, "max_local_relief_m": None, "required_resolution_m": None,
            "connectivity": None, "profile": "CONSERVATIVE", "include_alternative": True, "notes": "",
        }
        m = re.search(r"slopes?\s+(?:above|over|steeper than|greater than|more than|>)\s*" + _NUM, t) or \
            re.search(r"(?:max(?:imum)?\s+slope|slope\s+(?:limit|max(?:imum)?))\s*(?:of|:|=)?\s*" + _NUM, t) or \
            re.search(_NUM + r"\s*(?:°|deg(?:rees?)?)\s*(?:max(?:imum)?|slope)", t)
        if m:
            out["max_slope_deg"] = float(m.group(1))
        if re.search(r"smooth|less rough|lower roughness|avoid rough", t):
            out["prefer_lower_roughness"] = True
        if re.search(r"return (?:path|route|trip)|way back|back to (?:the )?base|round trip", t):
            out["require_return_route"] = True
        m = re.search(r"(?:buffer|keep|stay)\s+(?:of\s+)?(?:at least\s+)?" + _NUM + r"\s*(km|m)\b", t)
        if m:
            out["hazard_buffer_m"] = float(m.group(1)) * (1000 if m.group(2) == "km" else 1)
        m = re.search(r"(?:resolution|dem)\s+(?:of\s+)?(?:at least|finer than|better than)?\s*" + _NUM + r"\s*(km|m)\b", t)
        if m:
            out["required_resolution_m"] = float(m.group(1)) * (1000 if m.group(2) == "km" else 1)
        if re.search(r"no diagonal|four[- ]direction|4[- ]connect", t):
            out["connectivity"] = 4
        if re.search(r"(?:go|walk|drive|cross|through|allow)[^.]*(?:unknown|unmapped|no[- ]data)", t) and not re.search(r"avoid[^.]*(?:unknown|no[- ]data)", t):
            out["allow_unknown_terrain"] = True  # rejected by validation: needs an explicit planner choice
        if re.search(r"ignore (?:the )?(?:known )?hazards|don't avoid hazards|do not avoid hazards", t):
            out["avoid_known_hazards"] = False  # rejected by validation
        return out


class OllamaProvider(AIProvider):
    """A model served by a local Ollama instance (free; nothing leaves the machine)."""

    name = "ollama"

    def __init__(self):
        self.base_url = getattr(settings, "AI_BASE_URL", "") or "http://127.0.0.1:11434"
        self.model = getattr(settings, "AI_MODEL", "") or "llama3.1"
        self.timeout = float(getattr(settings, "AI_TIMEOUT_S", 60))

    def available(self) -> tuple[bool, str]:
        from services import http_client

        try:
            http_client.get_json("Ollama", f"{self.base_url}/api/tags", timeout=3.0)
            return True, ""
        except http_client.ProviderError as exc:
            return False, f"Local model server not reachable at {self.base_url}: {exc}"

    def complete_json(self, task: str, system: str, user: str, schema: dict) -> ProviderResult:
        import urllib.error
        import urllib.request

        body = json.dumps({
            "model": self.model, "stream": False, "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(f"{self.base_url}/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - URL from settings
                doc = json.loads(resp.read(5_000_000))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Ollama request failed: {type(exc).__name__}") from exc
        text = (doc.get("message") or {}).get("content") or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("The local model did not return valid JSON", "AI_INVALID_OUTPUT") from exc
        return ProviderResult(data, self.name, self.model, str(doc.get("model", "")), raw_text=text)
