"""Application-side guardrails. Deterministic checks the LLM cannot waive."""
from typing import Any


class ToolValidationError(ValueError):
    pass


def _type_ok(expected: str, value: Any) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float)
    if expected == "boolean":
        return type(value) is bool
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_tool_args(schema: dict, args: Any) -> dict:
    """Validate tool arguments against the tool's schema.

    Unknown types are ignored (forward-compatible); extra arguments allowed.
    Raises ToolValidationError on any violation.
    """
    if not isinstance(args, dict):
        raise ToolValidationError("tool arguments must be an object")
    for name in schema.get("required", []):
        if name not in args:
            raise ToolValidationError(f"missing required argument: {name}")
    properties = schema.get("properties", {})
    for name, value in args.items():
        spec = properties.get(name)
        if not isinstance(spec, dict):
            continue
        if not _type_ok(spec.get("type", ""), value):
            raise ToolValidationError(
                f"argument {name!r} must be {spec.get('type')}"
            )
    return args
