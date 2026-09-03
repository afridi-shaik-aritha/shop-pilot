"""Checkout preparation, explicit confirmation gate, idempotent mock orders."""
import hashlib
import uuid

from app.cart.service import CartService
from app.catalog.service import ProductNotFound, ProductService
from app.checkout.confirmation import cart_snapshot, snapshot_token
from app.models import Product
from app.state.models import Cart, Checkout, ConfirmationStatus, Order


class ConfirmationError(ValueError):
    pass


class StaleCheckoutError(ValueError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class CheckoutService:
    def __init__(self, carts: CartService) -> None:
        self._carts = carts

    def prepare(self, cart: Cart) -> Checkout:
        totals = self._carts.totals(cart)
        return Checkout(
            checkout_id=_new_id("C"),
            cart_snapshot=Cart(
                items=[i.model_copy() for i in cart.items], currency=cart.currency
            ),
            status=ConfirmationStatus.CHECKOUT_PREPARED,
            confirmation_token="",
            total=totals["total"],
        )

    def request_confirmation(self, checkout: Checkout) -> Checkout:
        if checkout.status != ConfirmationStatus.CHECKOUT_PREPARED:
            raise ConfirmationError(
                f"cannot request confirmation from {checkout.status}"
            )
        items, total = cart_snapshot(checkout.cart_snapshot, checkout.total)
        checkout.confirmation_token = snapshot_token(items, total)
        checkout.status = ConfirmationStatus.AWAITING_CONFIRMATION
        return checkout

    def confirm(self, checkout: Checkout, token: str) -> Checkout:
        if checkout.status != ConfirmationStatus.AWAITING_CONFIRMATION:
            raise ConfirmationError(
                f"cannot confirm from {checkout.status}; explicit confirmation required"
            )
        items, total = cart_snapshot(checkout.cart_snapshot, checkout.total)
        if token != snapshot_token(items, total):
            raise ConfirmationError("confirmation token does not match this checkout")
        checkout.status = ConfirmationStatus.CONFIRMED
        return checkout

    def cancel(self, checkout: Checkout) -> Checkout:
        checkout.status = ConfirmationStatus.REJECTED
        return checkout


class MockPaymentAdapter:
    """Deterministic sandbox payment. Transaction id derives from the idempotency key."""

    def charge(self, amount: float, idempotency_key: str) -> dict:
        txn = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12]
        return {"status": "captured", "amount": amount, "txn_id": f"TXN-{txn}"}


class OrderService:
    def __init__(
        self, products: ProductService, payment: MockPaymentAdapter | None = None
    ) -> None:
        self._products = products
        self._payment = payment or MockPaymentAdapter()
        self._by_key: dict[str, Order] = {}

    def place_order(
        self, checkout: Checkout, idempotency_key: str, catalog: list[Product]
    ) -> Order:
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        if checkout.status != ConfirmationStatus.CONFIRMED:
            raise ConfirmationError("order requires explicit confirmation first")
        live = {p.product_id: p for p in catalog}
        for item in checkout.cart_snapshot.items:
            product = live.get(item.product_id)
            if product is None:
                raise StaleCheckoutError(f"product gone: {item.product_id}")
            try:
                self._products.get_product(item.product_id)
            except ProductNotFound:
                raise StaleCheckoutError(
                    f"product gone: {item.product_id}"
                ) from None
            if not (product.availability and product.stock >= item.quantity):
                raise StaleCheckoutError(f"unavailable now: {item.product_id}")
            if product.price != item.unit_price:
                raise StaleCheckoutError(f"price changed: {item.product_id}")
        payment = self._payment.charge(checkout.total, idempotency_key)
        assert payment["status"] == "captured"
        checkout.status = ConfirmationStatus.PLACING_ORDER
        order = Order(
            order_id=_new_id("O"),
            checkout_id=checkout.checkout_id,
            items=[i.model_copy() for i in checkout.cart_snapshot.items],
            total=checkout.total,
            status="COMPLETED",
            idempotency_key=idempotency_key,
        )
        checkout.status = ConfirmationStatus.COMPLETED
        self._by_key[idempotency_key] = order
        return order
