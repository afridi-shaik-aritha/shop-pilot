"""Checkout preparation, explicit confirmation gate, idempotent mock orders."""
import hashlib
import hmac
import math
import threading
import uuid
from typing import TYPE_CHECKING, Protocol

from app.cart.service import CartService
from app.catalog.service import ProductNotFound, ProductService
from app.checkout.confirmation import new_confirmation_token
from app.models import Product
from app.state.models import Cart, Checkout, ConfirmationStatus, Order

if TYPE_CHECKING:
    from app.state.sqlite_store import SqliteStore


class ConfirmationError(ValueError):
    pass


class StaleCheckoutError(ValueError):
    pass


class SessionNotFound(FileNotFoundError):
    pass


class OrderNotFound(KeyError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _prices_equal(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=0.005)


def secrets_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a), str(b))


class CheckoutService:
    def __init__(self, carts: CartService) -> None:
        self._carts = carts

    def prepare(self, cart: Cart) -> Checkout:
        if not cart.items:
            raise ConfirmationError("cart is empty")
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
        if not checkout.cart_snapshot.items:
            raise ConfirmationError("cart is empty")
        checkout.confirmation_token = new_confirmation_token()
        checkout.status = ConfirmationStatus.AWAITING_CONFIRMATION
        return checkout

    def confirm(self, checkout: Checkout, token: str) -> Checkout:
        if checkout.status != ConfirmationStatus.AWAITING_CONFIRMATION:
            raise ConfirmationError(
                f"cannot confirm from {checkout.status}; explicit confirmation required"
            )
        if not checkout.confirmation_token or not token:
            raise ConfirmationError("confirmation token does not match this checkout")
        if not secrets_compare(token, checkout.confirmation_token):
            raise ConfirmationError("confirmation token does not match this checkout")
        checkout.status = ConfirmationStatus.CONFIRMED
        return checkout

    def cancel(self, checkout: Checkout) -> Checkout:
        if checkout.status in (
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.COMPLETED,
            ConfirmationStatus.PLACING_ORDER,
        ):
            raise ConfirmationError(
                f"cannot cancel from {checkout.status}"
            )
        checkout.status = ConfirmationStatus.REJECTED
        checkout.confirmation_token = ""
        return checkout


class MockPaymentAdapter:
    """Deterministic sandbox payment. Transaction id derives from the idempotency key."""

    def charge(self, amount: float, idempotency_key: str) -> dict:
        txn = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12]
        return {"status": "captured", "amount": amount, "txn_id": f"TXN-{txn}"}


class OrderStore(Protocol):
    """Idempotency + order record backend (in-memory default, SQLite for API)."""

    def get_by_key(self, key: str) -> Order | None:
        ...

    def save(self, order: Order) -> None:
        ...


class DictOrderStore:
    """In-memory records (tests, CLI, single-process use)."""

    def __init__(self) -> None:
        self._by_key: dict[str, Order] = {}
        self._lock = threading.Lock()

    def get_by_key(self, key: str) -> Order | None:
        with self._lock:
            return self._by_key.get(key)

    def save(self, order: Order) -> None:
        with self._lock:
            self._by_key[order.idempotency_key] = order


class SqliteOrderStore:
    """Durable records shared across processes/restarts (API runtime)."""

    def __init__(self, db: "SqliteStore") -> None:
        self._db = db

    def get_by_key(self, key: str) -> Order | None:
        return self._db.get_order_by_key(key)

    def save(self, order: Order) -> None:
        self._db.save_order(order)


class OrderService:
    def __init__(
        self,
        products: ProductService,
        payment: MockPaymentAdapter | None = None,
        store: OrderStore | None = None,
        catalog_store=None,
    ) -> None:
        self._products = products
        self._payment = payment or MockPaymentAdapter()
        self._store = store or DictOrderStore()
        self._catalog_store = catalog_store
        self._lock = threading.Lock()

    @staticmethod
    def scope_key(session_id: str | None, key: str) -> str:
        """Namespace idempotency keys per session so one session can never
        replay or read another session's order."""
        if session_id:
            return f"{session_id}:{key}"
        return key

    def place_order(
        self, checkout: Checkout, idempotency_key: str, catalog: list[Product],
        session_id: str | None = None,
    ) -> Order:
        namespaced = self.scope_key(session_id, idempotency_key)
        with self._lock:
            existing = self._store.get_by_key(namespaced)
            if existing is not None:
                return existing
            if checkout.status != ConfirmationStatus.CONFIRMED:
                raise ConfirmationError("order requires explicit confirmation first")
            live = {p.product_id: p for p in catalog}
            for item in checkout.cart_snapshot.items:
                product = live.get(item.product_id)
                if product is None:
                    raise StaleCheckoutError(f"product gone: {item.product_id}")
                if not (product.availability and product.stock >= item.quantity):
                    raise StaleCheckoutError(f"unavailable now: {item.product_id}")
                if not _prices_equal(product.price, item.unit_price):
                    raise StaleCheckoutError(f"price changed: {item.product_id}")
            # Atomic stock decrement (when a catalog store is wired): reserve
            # each line before charging; compensate already-decremented lines
            # if any line cannot be fulfilled so partial orders never happen.
            decremented: list = []
            if self._catalog_store is not None:
                for item in checkout.cart_snapshot.items:
                    ok = self._catalog_store.decrement_stock(
                        item.product_id, item.quantity
                    )
                    if not ok:
                        for pid, qty in decremented:
                            try:
                                prod = self._catalog_store.get_product(pid)
                                prod.stock += qty
                                prod.availability = True
                                self._catalog_store.upsert_product(prod)
                            except Exception:
                                pass
                        raise StaleCheckoutError(
                            f"unavailable now: {item.product_id}"
                        )
                    decremented.append((item.product_id, item.quantity))
            payment = self._payment.charge(checkout.total, namespaced)
            if payment.get("status") != "captured":
                raise StaleCheckoutError("payment was not captured")
            checkout.status = ConfirmationStatus.PLACING_ORDER
            order = Order(
                order_id=_new_id("O"),
                checkout_id=checkout.checkout_id,
                items=[i.model_copy() for i in checkout.cart_snapshot.items],
                total=checkout.total,
                status="COMPLETED",
                idempotency_key=namespaced,
            )
            checkout.status = ConfirmationStatus.COMPLETED
            self._store.save(order)
            return order
