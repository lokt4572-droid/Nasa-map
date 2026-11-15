"""Route explanations from the structured route result.

The explanation is built from FACTS extracted from the planner's result. A language model may
reword them, but its text is checked: every number it contains must appear in the facts
(within rounding). An explanation with an unsupported number is discarded and the
deterministic template is returned instead. Explanations are not physical evidence."""
from __future__ import annotations

import hashlib
import json
import re

from apps.ai.models import AiInteraction
from apps.ai.providers import get_provider
from apps.ai.providers.base import ProviderError

SECTIONS = ("summary", "cost_factors", "uncertain_data", "alternatives", "limitations")


def facts_from_result(result: dict) -> dict:
    """The only information an explanation may use (numbers rounded as they will be shown)."""
    route = result.get("route") or {}
    m = route.get("metrics") or {}
    dq = result.get("data_quality") or {}
    prof = result.get("profile") or {}
    alt = result.get("alternative_route")
    table = result.get("comparison_table") or {}

    def r(v, n=1):
        return None if v is None else round(float(v), n)

    return {
        "status": result.get("calculation_status") or result.get("status"),
        "route_class": result.get("route_class"),
        "route_label": result.get("route_label"),
        "planning_level": (result.get("planning_level") or {}).get("name"),
        "dem": dq.get("dataset"),
        "dem_resolution_m": r(dq.get("resolution_m")),
        "grid_cell_m": r(dq.get("grid_cell_m")),
        "distance_km": r((m.get("distance_m") or 0) / 1000, 2) if m else None,
        "total_ascent_m": r(m.get("total_ascent_m"), 0),
        "total_descent_m": r(m.get("total_descent_m"), 0),
        "maximum_slope_deg": r(m.get("maximum_slope_deg")),
        "average_slope_deg": r(m.get("average_slope_deg")),
        "roughness_tri_mean_m": r(m.get("roughness_tri_mean_m")),
        "hazard_exposure_m": r(m.get("hazard_exposure_m"), 0),
        "unknown_terrain_pct": r(m.get("nodata_pct_along_route")),
        "terrain_cost_share_pct": r(100 * m["terrain_cost"] / m["cost"], 0) if m.get("cost") else None,
        "profile": prof.get("id"),
        "max_slope_limit_deg": r(prof.get("max_slope_deg")),
        "hazards_considered": result.get("hazards_considered"),
        "alternative": None if not alt else {
            "distance_km": r(alt["metrics"]["distance_m"] / 1000, 2),
            "maximum_slope_deg": r(alt["metrics"].get("maximum_slope_deg")),
            "terrain_cost_difference": r(alt["metrics"]["terrain_cost"] - m.get("terrain_cost", 0), 0) if m else None,
        },
        "alternative_note": result.get("alternative_note"),
        "descriptors": {c["name"]: c["descriptors"] for c in table.get("routes", [])},
        "warnings": list(result.get("warnings") or []),
        "failure_reason": result.get("reason"),
    }


def template_explanation(f: dict) -> dict:
    """Deterministic explanation from the facts (always available)."""
    if f.get("status") != "CALCULATED":
        return {
            "summary": f"No route was calculated ({f.get('status')}). {f.get('failure_reason') or ''}".strip(),
            "cost_factors": [], "uncertain_data": [], "alternatives": [],
            "limitations": list(f.get("warnings") or []),
        }
    s = (f"Route A is the lowest-cost route the planner found on {f['dem']} "
         f"({f['dem_resolution_m']} m DEM, {f['grid_cell_m']} m planning cells): {f['distance_km']} km, "
         f"{f['total_ascent_m']:.0f} m of ascent, maximum slope {f['maximum_slope_deg']} deg "
         f"(profile limit {f['max_slope_limit_deg']} deg).")
    factors = []
    if f.get("terrain_cost_share_pct") is not None:
        factors.append(f"{f['terrain_cost_share_pct']:.0f}% of the calculated cost comes from slope, roughness, hazard proximity and uncertainty; the rest is distance.")
    if f.get("average_slope_deg") is not None:
        factors.append(f"Average slope along the route: {f['average_slope_deg']} deg.")
    if f.get("roughness_tri_mean_m") is not None:
        factors.append(f"Mean roughness (TRI) along the route: {f['roughness_tri_mean_m']} m.")
    if f.get("hazard_exposure_m"):
        factors.append(f"{f['hazard_exposure_m']:.0f} m of the route lie in the proximity zone of known hazards.")
    uncertain = []
    if f.get("unknown_terrain_pct"):
        uncertain.append(f"{f['unknown_terrain_pct']}% of the route crosses cells without DEM data (marked unverified).")
    else:
        uncertain.append("Every cell on the route has a DEM value; smaller features than the planning cell are not represented.")
    alts = []
    if f.get("alternative"):
        a = f["alternative"]
        alts.append(f"Route B: {a['distance_km']} km, maximum slope {a['maximum_slope_deg']} deg, "
                    f"terrain cost {a['terrain_cost_difference']:+.0f} relative to Route A. It was not selected because its calculated cost is higher.")
    elif f.get("alternative_note"):
        alts.append(f["alternative_note"])
    return {"summary": s, "cost_factors": factors, "uncertain_data": uncertain, "alternatives": alts,
            "limitations": list(f.get("warnings") or [])}


_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?")


def _numbers(obj) -> list[float]:
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _numbers(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        out += [float(x.replace(",", "")) for x in _NUMBER.findall(obj)]
    return out


def ungrounded_numbers(text_obj, facts: dict) -> list[float]:
    """Numbers in the explanation that do not match a fact (absolute or 1 % tolerance, plus
    the small ordinals 0..3 and 'Route A/B' style labels)."""
    known = _numbers(facts)
    bad = []
    for n in _numbers(text_obj):
        if abs(n) <= 3 and float(n).is_integer():
            continue
        if not any(abs(n - k) <= max(0.051, 0.01 * abs(k)) or abs(abs(n) - abs(k)) <= 0.051 for k in known):
            bad.append(n)
    return bad


def _schema() -> dict:
    lst = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": {"summary": {"type": "string"}, "cost_factors": lst, "uncertain_data": lst,
            "alternatives": lst, "limitations": lst}, "required": list(SECTIONS), "additionalProperties": False}


SYSTEM = (
    "You explain a computed planetary route to a mission planner. Use ONLY the facts in the JSON you are given; "
    "do not add numbers, places, hazards or measurements that are not in it, and do not estimate travel time. "
    "Never call a route safe, guaranteed or recommended for crew; say 'lower calculated cost' instead. "
    "Mention data limitations plainly. Return the JSON object described by the schema."
)


def explain(result: dict, route_id: int | None = None) -> dict:
    facts = facts_from_result(result)
    raw = json.dumps(facts, sort_keys=True, default=str)
    rec = AiInteraction(kind=AiInteraction.Kind.EXPLAIN, input_ref="sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
                        route_id=route_id, provider="template", model="deterministic-template")
    explanation = template_explanation(facts)
    generator = {"name": "template", "is_language_model": False}
    validation: dict = {"accepted": True, "checks": ["deterministic template from route facts"]}
    provider = None
    try:
        provider = get_provider()
    except ProviderError:
        provider = None
    if provider is not None and provider.is_language_model:
        ok, why = provider.available()
        rec.provider, rec.model = provider.name, getattr(provider, "model", "")
        if ok:
            try:
                out = provider.complete_json("explain", SYSTEM, raw, _schema())
                rec.model_version, rec.structured_result = out.model_version, out.data
                bad = ungrounded_numbers(out.data, facts)
                banned = re.search(r"\b(safe|safest|guaranteed)\b", json.dumps(out.data), re.I)
                if set(out.data) != set(SECTIONS):
                    validation = {"accepted": False, "reason": "wrong sections"}
                elif bad:
                    validation = {"accepted": False, "reason": f"numbers not present in the route result: {bad[:5]}"}
                elif banned:
                    validation = {"accepted": False, "reason": "uses a safety claim word"}
                else:
                    explanation = out.data
                    generator = {"name": provider.name, "model": rec.model, "is_language_model": True}
                    validation = {"accepted": True, "checks": ["schema", "every number grounded in the route result", "no safety claims"]}
            except ProviderError as exc:
                validation = {"accepted": False, "reason": str(exc), "code": exc.code}
        else:
            validation = {"accepted": False, "reason": why, "code": "AI_UNAVAILABLE"}
        if not validation["accepted"]:
            validation["fallback"] = "deterministic template used instead"
    rec.accepted = generator["name"] != "template" or not (provider and provider.is_language_model)
    rec.validation = validation
    rec.save()
    return {
        "explanation": explanation,
        "generator": generator,
        "validation": validation,
        "facts": facts,
        "interaction_id": rec.id,
        "note": "Explanation of the planner's numbers; it is not evidence about the terrain and the route is not a safety assessment.",
    }
