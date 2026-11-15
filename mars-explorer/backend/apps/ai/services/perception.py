"""AI terrain perception: status, and storage of detections as UNCERTAIN observations.

This build ships NO hazard-detection model. Models trained on Earth imagery cannot be assumed to
work on Mars or the Moon, and no planetary model validated on labelled orbital imagery is
configured, so perception is reported UNAVAILABLE. Detections from an external, separately
validated model can be ingested when the operator enables it; they are stored as
MODEL_ESTIMATED / UNVERIFIED hazards and never block routes until a person confirms them.
"""
from __future__ import annotations

from django.conf import settings

DETECTION_CLASSES = {"BOULDER_FIELD", "CRATER", "SAND_DUNE", "STEEP_SLOPE", "ROUGH_TERRAIN", "UNKNOWN_SURFACE"}
VALIDATION_STATES = {"UNVALIDATED", "VALIDATED_ON_HOLDOUT", "VALIDATED_FIELD"}


def status() -> dict:
    enabled = bool(getattr(settings, "AI_PERCEPTION_INGEST_ENABLED", False))
    return {
        "status": "UNAVAILABLE" if not enabled else "INGEST_ONLY",
        "model": None,
        "reason": ("No validated planetary hazard-detection model is configured. Earth-trained detectors are not "
                   "assumed to transfer to Mars or lunar imagery."),
        "ingest_enabled": enabled,
        "classes": sorted(DETECTION_CLASSES),
        "storage": "MODEL_ESTIMATED / UNVERIFIED hazards; not hard route constraints until confirmed by a person",
    }
