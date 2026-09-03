import pytest

from app.guardrails import ToolValidationError, validate_tool_args

SCHEMA = {
    "name": "add_to_cart",
    "type": "object",
    "properties": {
        "product_id": {"type": "string"},
        "quantity": {"type": "integer"},
    },
    "required": ["product_id"],
}


def test_valid_args_pass_through():
    args = {"product_id": "P01", "quantity": 2}
    assert validate_tool_args(SCHEMA, args) == args


def test_missing_required_raises():
    with pytest.raises(ToolValidationError):
        validate_tool_args(SCHEMA, {"quantity": 1})


def test_wrong_types_raise():
    with pytest.raises(ToolValidationError):
        validate_tool_args(SCHEMA, {"product_id": "P01", "quantity": "many"})
    with pytest.raises(ToolValidationError):
        validate_tool_args(SCHEMA, {"product_id": "P01", "quantity": True})


def test_unknown_types_ignored_and_extras_allowed():
    schema = {
        "name": "t",
        "properties": {"mystery": {"type": "future-type"}},
        "required": [],
    }
    args = {"mystery": "anything", "extra": 1}
    assert validate_tool_args(schema, args) == args
