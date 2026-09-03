"""Cart operations. All mutations are explicit; unit prices are catalog facts."""
from app.catalog.service import ProductNotFound, ProductService
from app.state.models import Cart, CartItem

FREE_SHIPPING_THRESHOLD = 5000.0
SHIPPING_FLAT = 49.0
TAX_RATE = 0.18


class CartError(ValueError):
    pass


class CartService:
    def __init__(self, products: ProductService) -> None:
        self._products = products

    def add_to_cart(self, cart: Cart, product_id: str, quantity: int) -> Cart:
        if quantity < 1:
            raise CartError(f"quantity must be >= 1, got {quantity}")
        try:
            product = self._products.get_product(product_id)
        except ProductNotFound:
            raise CartError(f"unknown product: {product_id}") from None
        for item in cart.items:
            if item.product_id == product_id:
                item.quantity += quantity
                return cart
        cart.items.append(
            CartItem(product_id=product_id, quantity=quantity, unit_price=product.price)
        )
        return cart

    def remove_from_cart(self, cart: Cart, product_id: str) -> Cart:
        for i, item in enumerate(cart.items):
            if item.product_id == product_id:
                cart.items.pop(i)
                return cart
        raise CartError(f"not in cart: {product_id}")

    def update_quantity(self, cart: Cart, product_id: str, quantity: int) -> Cart:
        if quantity < 0:
            raise CartError(f"quantity must be >= 0, got {quantity}")
        for item in cart.items:
            if item.product_id == product_id:
                if quantity == 0:
                    cart.items.remove(item)
                else:
                    item.quantity = quantity
                return cart
        raise CartError(f"not in cart: {product_id}")

    def clear_cart(self, cart: Cart) -> Cart:
        cart.items.clear()
        return cart

    def totals(self, cart: Cart) -> dict:
        subtotal = cart.subtotal()
        if subtotal == 0:
            shipping = 0.0
        elif subtotal >= FREE_SHIPPING_THRESHOLD:
            shipping = 0.0
        else:
            shipping = SHIPPING_FLAT
        tax = round((subtotal + shipping) * TAX_RATE, 2)
        return {
            "subtotal": subtotal,
            "shipping": shipping,
            "tax": tax,
            "total": round(subtotal + shipping + tax, 2),
        }
