"""Structured shopping intent extracted deterministically before retrieval."""
import re

from pydantic import BaseModel, Field

_KNOWN_CATEGORIES = [
    "wireless headphones",
    "wired earphones",
    "bluetooth speaker",
    "smartwatch",
]
_BUDGET_RES = [
    re.compile(r"under\s+[₹Rs]*\s*(\d[\d,]*)", re.IGNORECASE),
    re.compile(r"below\s+[₹Rs]*\s*(\d[\d,]*)", re.IGNORECASE),
    re.compile(r"budget\s+[₹Rs]*\s*(\d[\d,]*)", re.IGNORECASE),
]


class IntentConstraints(BaseModel):
    category: str | None = None
    max_price: float | None = None
    desired_attributes: list[str] = Field(default_factory=list)
    review_preference: bool = False


def parse_intent(text: str) -> IntentConstraints:
    lowered = text.lower()
    category = next((c for c in _KNOWN_CATEGORIES if c in lowered), None)
    max_price: float | None = None
    for rx in _BUDGET_RES:
        m = rx.search(text)
        if m:
            max_price = float(m.group(1).replace(",", ""))
            break
    attrs = [w for w in ["battery", "bass", "noise", "comfort", "warranty"] if w in lowered]
    return IntentConstraints(
        category=category,
        max_price=max_price,
        desired_attributes=attrs,
        review_preference="review" in lowered or "rating" in lowered,
    )
