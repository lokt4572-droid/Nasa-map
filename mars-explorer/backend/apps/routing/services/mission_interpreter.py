"""Mission interpretation lives in the optional AI app (``apps.ai``); re-exported here so the
routing package keeps one entry point. The routing engine does not depend on it."""
from apps.ai.services.mission_interpreter import interpret, to_plan_fields, validate_constraints  # noqa: F401
