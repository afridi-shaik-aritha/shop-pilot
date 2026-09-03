"""Snapshot-bound confirmation tokens. Token = sha256 hex[:16] of canonical snapshot."""
import hashlib
import json

from app.state.models import Cart


def snapshot_token(items: list[dict], total: float) -> str:
    canonical = json.dumps({"items": items, "total": total}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def cart_snapshot(cart: Cart, total: float) -> tuple[list[dict], float]:
    items = [
        {"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
        for i in sorted(cart.items, key=lambda x: x.product_id)
    ]
    return items, round(total, 2)
