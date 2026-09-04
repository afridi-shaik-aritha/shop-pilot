"""Deterministic grounding checks: every product id and number in the final
text must already appear in the tool-result trace."""
import re

# Numbers must look like real prices/ratings: at least 2 digits total, with
# optional commas/decimals. Single stray digits (e.g. the "5" in "X5" or "01"
# in "P01") are not evidence and are ignored.
_NUMBER_RE = re.compile(r"\b\d[\d,]*\.?\d*\b")
_ID_RE = re.compile(r"\bP\d{2}\b")


def _normalize_number(raw: str) -> str | None:
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 2:
        return None
    try:
        return str(float(cleaned))
    except ValueError:
        return None


def numbers_in(text: str) -> list[str]:
    out = []
    for raw in _NUMBER_RE.findall(text or ""):
        norm = _normalize_number(raw)
        if norm is not None:
            out.append(norm)
    return out


def ids_in(text: str) -> list[str]:
    return sorted(set(_ID_RE.findall(text or "")))


def _trace_numbers(trace_text: str) -> set[str]:
    found: set[str] = set()
    for raw in _NUMBER_RE.findall(trace_text or ""):
        norm = _normalize_number(raw)
        if norm is not None:
            found.add(norm)
    # Also index raw currency-adjacent forms ($84.99 vs 84.99) via normalization.
    return found


def grounding_ok(text: str, trace_text: str) -> tuple[bool, dict]:
    trace_nums = _trace_numbers(trace_text)
    missing_numbers = [n for n in numbers_in(text) if n not in trace_nums]
    missing_ids = [i for i in ids_in(text) if i not in (trace_text or "")]
    ok = not missing_numbers and not missing_ids
    return ok, {"missing_numbers": missing_numbers, "missing_ids": missing_ids}
