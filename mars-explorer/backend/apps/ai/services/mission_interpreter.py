"""Natural-language mission preferences -> a validated RouteConstraints object.

The model (or the rule parser) only proposes constraint VALUES. This module decides what is
accepted. It rejects unsupported fields, out-of-range numbers, missing mandatory constraints,
any coordinate or geometry, and requests to bypass safety rules. It never produces a path:
accepted constraints go to the deterministic planner, which computes the route on the DEM.

The values are user-selected planning assumptions, not validated astronaut safety limits.
"""
from __future__ import annotations

import hashlib
import math
import re

from apps.ai.models import AiInteraction
from apps.ai.providers import get_provider
from apps.ai.providers.base import ProviderError

MAX_INSTRUCTION_CHARS = 2000

# field: (type, min, max) — None bounds = no numeric bound; "bool"/"enum" handled separately.
NUMERIC = {
    "max_slope_deg": (1.0, 45.0),
    "hazard_buffer_m": (0.0, 100_000.0),
    "max_roughness_m": (0.0, 10_000.0),
    "max_local_relief_m": (0.0, 100_000.0),
    "required_resolution_m": (0.01, 1_000_000.0),
}
BOOLEAN = {"allow_unknown_terrain", "avoid_known_hazards", "prefer_lower_roughness", "require_return_route", "include_alternative"}
ENUM = {"profile": {"CONSERVATIVE", "STANDARD"}, "connectivity": {4, 8}}
TEXT = {"notes": 500}
MANDATORY = ("max_slope_deg", "allow_unknown_terrain", "avoid_known_hazards")
ALLOWED = set(NUMERIC) | BOOLEAN | set(ENUM) | set(TEXT)
COORDINATE_KEYS = re.compile(r"(lon|lat|coord|geometry|path|waypoint|start|end|destination|position|point|xy)", re.I)
BYPASS = re.compile(
    r"\b(ignore|bypass|disable|skip|override|turn off|switch off|remove|without)\b[^.]{0,40}"
    r"\b(safety|validation|validator|constraints?|checks?|hazards?|limits?|rules?)\b", re.I)

DEFAULTS_FOR_MODEL = {"max_slope_deg": 15.0, "allow_unknown_terrain": False, "avoid_known_hazards": True}


def _schema() -> dict:
    """JSON schema given to a language model. Bounds are checked here, not trusted to the model."""
    def nullable(t):
        return {"anyOf": [{"type": t}, {"type": "null"}]}

    props = {
        "max_slope_deg": {"type": "number"},
        "allow_unknown_terrain": {"type": "boolean"},
        "avoid_known_hazards": {"type": "boolean"},
        "prefer_lower_roughness": {"type": "boolean"},
        "require_return_route": {"type": "boolean"},
        "include_alternative": {"type": "boolean"},
        "hazard_buffer_m": nullable("number"),
        "max_roughness_m": nullable("number"),
        "max_local_relief_m": nullable("number"),
        "required_resolution_m": nullable("number"),
        "connectivity": {"anyOf": [{"type": "integer", "enum": [4, 8]}, {"type": "null"}]},
        "profile": {"type": "string", "enum": ["CONSERVATIVE", "STANDARD"]},
        "notes": {"type": "string"},
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SYSTEM = (
    "You convert a planetary traverse planner's route preferences into planning constraints. "
    "Return only the JSON object described by the schema. Use null for anything the user did not state. "
    f"If the user gives no slope limit use max_slope_deg {DEFAULTS_FOR_MODEL['max_slope_deg']}. "
    "Keep allow_unknown_terrain false and avoid_known_hazards true unless the user explicitly asks otherwise; "
    "the application decides whether such a request is acceptable. Never output coordinates, places, paths or "
    "geometry, and never invent terrain information. Units: degrees for slopes, metres for distances. "
    "In notes, restate the user's preferences in one short sentence without numbers that the user did not give."
)


class InterpretationRejected(Exception):
    def __init__(self, code: str, problems: list[str]):
        super().__init__("; ".join(problems))
        self.code = code
        self.problems = problems


def validate_constraints(data: object) -> dict:
    """Strict validation. Returns the cleaned constraints or raises InterpretationRejected."""
    if not isinstance(data, dict):
        raise InterpretationRejected("INVALID_OUTPUT", ["the result is not a JSON object"])
    problems: list[str] = []
    coords = [k for k in data if k not in ALLOWED and COORDINATE_KEYS.search(str(k))]
    if coords:
        raise InterpretationRejected("COORDINATE_CHANGE_ATTEMPT", [f"coordinates/geometry are not accepted from the assistant: {sorted(coords)}"])
    unknown = sorted(set(data) - ALLOWED)
    if unknown:
        problems.append(f"unsupported fields: {unknown}")
    for k in MANDATORY:
        if data.get(k) is None:
            problems.append(f"missing mandatory constraint: {k}")
    out: dict = {}
    for k, (lo, hi) in NUMERIC.items():
        v = data.get(k)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            problems.append(f"{k} must be a number")
        elif not lo <= v <= hi:
            problems.append(f"{k}={v} outside {lo}..{hi}")
        else:
            out[k] = float(v)
    for k in BOOLEAN:
        v = data.get(k)
        if v is None:
            continue
        if not isinstance(v, bool):
            problems.append(f"{k} must be true or false")
        else:
            out[k] = v
    for k, allowed in ENUM.items():
        v = data.get(k)
        if v is None:
            continue
        if v not in allowed or isinstance(v, bool):
            problems.append(f"{k} must be one of {sorted(allowed, key=str)}")
        else:
            out[k] = v
    notes = data.get("notes")
    if notes is not None:
        if not isinstance(notes, str) or len(notes) > TEXT["notes"]:
            problems.append("notes must be a short string")
        elif BYPASS.search(notes):
            problems.append("the assistant's notes ask to bypass safety rules")
        else:
            out["notes"] = notes
    if problems:
        raise InterpretationRejected("INVALID_CONSTRAINTS", problems)
    # Rules the assistant may not override (checked after the shape is valid).
    if out.get("allow_unknown_terrain"):
        raise InterpretationRejected("SAFETY_RULE", [
            "crossing terrain without DEM data cannot be enabled through the assistant; choose the STANDARD profile "
            "with 'allow marked unknown terrain' in the route planner if you accept unverified segments"])
    if out.get("avoid_known_hazards") is False:
        raise InterpretationRejected("SAFETY_RULE", ["known hazards are always avoided; the assistant cannot disable that"])
    return out


def to_plan_fields(c: dict) -> dict:
    """Validated constraints -> fields of the route plan request (planner vocabulary)."""
    out = {
        "profile": c.get("profile", "CONSERVATIVE"),
        "max_slope_deg": c["max_slope_deg"],
        "unknown_data_policy": "REJECT",
        "include_return": bool(c.get("require_return_route", False)),
        "include_alternative": bool(c.get("include_alternative", True)),
        "prefer_lower_roughness": bool(c.get("prefer_lower_roughness", False)),
    }
    for k in ("hazard_buffer_m", "max_roughness_m", "max_local_relief_m", "required_resolution_m", "connectivity"):
        if c.get(k) is not None:
            out[k] = c[k]
    return out


def input_ref(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def interpret(instruction: str) -> dict:
    """Instruction -> {"accepted", "constraints", "plan_fields", "provider", "interaction_id", ...}.

    Never raises for a bad instruction or bad model output: the outcome is recorded and returned
    with accepted=False and the reasons."""
    text = (instruction or "").strip()
    rec = AiInteraction(kind=AiInteraction.Kind.INTERPRET, input_ref=input_ref(text), provider="none")
    result: dict = {"accepted": False, "constraints": None, "plan_fields": None, "problems": [], "code": None}
    try:
        if not text or len(text) > MAX_INSTRUCTION_CHARS:
            raise InterpretationRejected("INVALID_INPUT", [f"instruction must be 1..{MAX_INSTRUCTION_CHARS} characters"])
        if BYPASS.search(text):
            raise InterpretationRejected("SAFETY_BYPASS_REQUEST", ["the instruction asks to bypass safety rules or validation; nothing was interpreted"])
        provider = get_provider()
        if provider is None:
            raise InterpretationRejected("AI_UNAVAILABLE", ["no AI provider is configured (AI_PROVIDER=none)"])
        ok, why = provider.available()
        rec.provider, rec.model = provider.name, getattr(provider, "model", "")
        if not ok:
            raise InterpretationRejected("AI_UNAVAILABLE", [why])
        out = provider.complete_json("interpret", SYSTEM, text, _schema())
        rec.model_version, rec.structured_result = out.model_version, out.data
        constraints = validate_constraints(out.data)
        result.update(accepted=True, constraints=constraints, plan_fields=to_plan_fields(constraints))
    except InterpretationRejected as exc:
        result.update(code=exc.code, problems=exc.problems)
    except ProviderError as exc:
        result.update(code=exc.code, problems=[str(exc)])
    rec.accepted = result["accepted"]
    rec.validation = {"accepted": result["accepted"], "code": result["code"], "problems": result["problems"]}
    rec.save()
    result.update(
        interaction_id=rec.id,
        provider={"name": rec.provider, "model": rec.model, "model_version": rec.model_version,
                  "is_language_model": rec.provider not in ("rules", "none")},
        note=("Constraints are user-selected planning assumptions, not validated astronaut safety limits. "
              "The route itself is computed by the deterministic planner on the DEM."),
    )
    return result
