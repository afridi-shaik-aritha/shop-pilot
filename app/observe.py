"""Run tracing with secret redaction.

Redacted: api keys, authorization headers, secrets, passwords, and
confirmation tokens (tokens are shown to the shopper only; traces keep them
redacted and audit via checkout/order ids instead).
"""
import uuid
from typing import Any

_REDACT_FRAGMENTS = ("api_key", "apikey", "authorization", "secret", "password",
                     "confirmation_token", "confirmation-token", "token")


def redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: (
                "***"
                if any(frag in str(key).lower() for frag in _REDACT_FRAGMENTS)
                else redact(value)
            )
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(value) for value in payload]
    return payload


class TraceRecorder:
    def __init__(self, db) -> None:
        self._db = db

    def record(self, kind: str, payload: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        self._db.save_trace(run_id, kind, redact(payload))
        return run_id
