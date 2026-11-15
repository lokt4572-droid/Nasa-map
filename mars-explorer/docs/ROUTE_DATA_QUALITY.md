# Route data quality (v0.4)

Every route response states what data it was computed on and what that data cannot show.

## Result fields

| Field | Meaning |
|---|---|
| `calculation_status` | CALCULATED, INSUFFICIENT_TERRAIN_DATA, START_OUTSIDE_COVERAGE, DESTINATION_OUTSIDE_COVERAGE, UNKNOWN_TERRAIN, INVALID_DATASET, NO_VALID_ROUTE, PROCESSING_ERROR |
| `route_class` | REGIONAL_PLANNING_ONLY (cells > 100 m, or any MOLA-derived DEM), SITE_RECONNAISSANCE (2–100 m), DETAILED_TRAVERSE_STUDY (≤ 2 m) |
| `planning_level` | 1 REGIONAL, 2 LOCAL, 3 DETAILED — set by the data actually used |
| `route_label` | CONSERVATIVE ROUTE, LOWER-COST ROUTE, PARTIALLY UNVERIFIED ROUTE, NO VALID ROUTE (never "safe") |
| `data_quality` | dataset, resolution_m, grid_cell_m, access (LOCAL/REMOTE_COG), provider quality_status, effective_accuracy (NOT_DOCUMENTED unless stated), coverage %, NoData %, unknown-terrain % along the route, latitude handling, resolution assessment |
| `metrics` | distance, 3-D distance, ascent, descent, maximum and average slope, mean/max TRI, distance near known hazards, % unknown terrain, cost, terrain cost |
| `warnings` | planning scope, decimation, NoData in the window, unverified segments, provider quality, catalogue notes |
| `route.validation` | independent re-check result (valid, problems, checked steps) |
| `comparison_table` | Route A vs B on the same DEM and profile, with neutral descriptors |

## Hazard provenance

Each hazard has `observation_class` (OBSERVED, INFERRED, USER_REPORTED, MODEL_ESTIMATED, UNKNOWN),
method, confidence (0–1, as stated by the reporter or model; not a scientific probability),
verification, planet, timestamp, optional image link and, for model output, the model, version,
source image, resolution and validation status. MODEL_ESTIMATED hazards are created UNVERIFIED and
do not block routes until a person confirms them.

DEM-derived candidates (`POST /api/v1/routes/hazards/derive/`): STEEP_SLOPE, ROUGH_TERRAIN and
MISSING_DATA areas from thresholds on the DEM — MODEL_ESTIMATED, not stored. CRATER, BOULDER_FIELD,
SAND_DUNE and UNKNOWN_SURFACE are **not** derived from a DEM threshold or from image brightness.

## What a route cannot tell you

- Anything smaller than about two grid cells (MOLA: ~30 km; CTX: ~40 m; HiRISE: ~2–3 m).
- Rocks, loose regolith, subsurface conditions, lighting, communications.
- Travel time (never estimated).
- Astronaut-scale safety: `astronaut_scale_route_safety` is always NOT_SUITABLE (cells > 1 m) or
  NOT_ASSESSED_NO_VALIDATED_MODEL.

## AI assistance

Optional. The interpreter turns text into validated constraints (rejects unsupported fields,
out-of-range values, coordinates, and requests to bypass safety rules; cannot enable unknown
terrain or disable hazard avoidance). Explanations use only the route's numbers; text with an
unsupported number or a safety claim is replaced by the deterministic template. Every call is
recorded (`AiInteraction`: provider, model, version, input hash, result, validation).
