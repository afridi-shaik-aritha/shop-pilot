"""State data models. The LLM never mutates these directly; services own all transitions."""
from enum import Enum

from pydantic import BaseModel, Field


class ConfirmationStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    CHECKOUT_PREPARED = "CHECKOUT_PREPARED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    REVALIDATING = "REVALIDATING"
    PLACING_ORDER = "PLACING_ORDER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CartItem(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)


class Cart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)
    currency: str = "INR"

    def subtotal(self) -> float:
        return round(sum(i.quantity * i.unit_price for i in self.items), 2)


class Checkout(BaseModel):
    checkout_id: str = Field(min_length=1)
    cart_snapshot: Cart
    status: ConfirmationStatus = ConfirmationStatus.CHECKOUT_PREPARED
    confirmation_token: str = ""
    total: float = Field(ge=0)


class Order(BaseModel):
    order_id: str = Field(min_length=1)
    checkout_id: str = Field(min_length=1)
    items: list[CartItem] = Field(default_factory=list)
    total: float = Field(ge=0)
    status: str = "COMPLETED"
    idempotency_key: str = ""


class ShoppingSession(BaseModel):
    session_id: str = Field(min_length=1)
    user_id: str = "anon"
    cart: Cart = Field(default_factory=Cart)
    checkout: Checkout | None = None
    order: Order | None = None
    history: list[dict] = Field(default_factory=list)
    # Recent plain-language turns ({"role": "user"|"assistant", "content": str})
    # replayed into /chat for multi-turn context; capped by the API layer.
    messages: list[dict] = Field(default_factory=list)
