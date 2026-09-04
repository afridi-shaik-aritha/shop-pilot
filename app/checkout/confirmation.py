"""Snapshot-bound confirmation tokens.

Tokens are cryptographically random per checkout (secrets module) and stored
server-side on the Checkout object. The snapshot helpers below are retained
for audit/binding checks: the token is only valid for the exact snapshot it
was issued for.
"""
import hashlib
import json
import secrets

from app.state.models import Cart


def new_confirmation_token() -> str:
    """Generate an unforgeable per-checkout confirmation token."""
    return secrets.token_urlsafe(12)


def snapshot_token(items: list[dict], total: float) -> str:
    canonical = json.dumps({"items": items, "total": total}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def cart_snapshot(cart: Cart, total: float) -> tuple[list[dict], float]:
    items = [
        {"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
        for i in sorted(cart.items, key=lambda x: x.product_id)
    ]
    return items, round(total, 2)
