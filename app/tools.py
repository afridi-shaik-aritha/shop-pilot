"""Tool registry. Each tool has a JSON schema and a pure function over (args, ctx).

ctx carries the mutable session objects for the current run:
{"cart": Cart, "checkout": Checkout | None}. Tools never touch the LLM.
"""
from dataclasses import dataclass
from typing import Any, Callable

from app.cart.service import CartService
from app.catalog.service import ProductService, ReviewService
from app.checkout.service import CheckoutService, OrderService
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products, load_reviews
from app.state.models import Cart


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    run: Callable[[dict, dict], Any]


def _s(name: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _cart_of(ctx: dict) -> Cart:
    return ctx.setdefault("cart", Cart())


def build_tools(
    index: ProductIndex,
    catalog: ProductService,
    carts: CartService,
    checkout: CheckoutService,
    orders: OrderService,
    products_path: str = "data/products.json",
    reviews_path: str = "data/reviews.json",
) -> dict[str, Tool]:
    reviews = ReviewService(load_reviews(reviews_path))

    def search_products(args: dict, ctx: dict) -> dict:
        filters = {k: v for k, v in args.get("filters", {}).items()}
        hits = index.search(args["query"], args.get("top_k", 5), filters or None)
        return {
            "products": [
                {
                    "product_id": r.product.product_id,
                    "name": r.product.name,
                    "price": r.product.price,
                    "rating": r.product.rating,
                    "score": round(r.score, 3),
                }
                for r in hits
            ]
        }

    def get_product(args: dict, ctx: dict) -> dict:
        return catalog.get_product(args["product_id"]).model_dump()

    def search_reviews(args: dict, ctx: dict) -> dict:
        return {
            "reviews": reviews.search_reviews(
                args["product_id"], args.get("query"), args.get("top_k", 5)
            )
        }

    def compare_products(args: dict, ctx: dict) -> dict:
        return catalog.compare_products(args["product_ids"])

    def add_to_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.add_to_cart(cart, args["product_id"], args.get("quantity", 1))
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def remove_from_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.remove_from_cart(cart, args["product_id"])
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def update_cart_quantity(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.update_quantity(cart, args["product_id"], args["quantity"])
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def get_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        return {**cart.model_dump(), "totals": carts.totals(cart)}

    def prepare_checkout(args: dict, ctx: dict) -> dict:
        co = checkout.prepare(_cart_of(ctx))
        co = checkout.request_confirmation(co)
        ctx["checkout"] = co
        return co.model_dump()

    def confirm_checkout(args: dict, ctx: dict) -> dict:
        co = ctx.get("checkout")
        if co is None:
            raise ValueError("no checkout prepared")
        return checkout.confirm(co, args["confirmation_token"]).model_dump()

    def place_order(args: dict, ctx: dict) -> dict:
        co = ctx.get("checkout")
        if co is None:
            raise ValueError("no checkout prepared")
        catalog_live = load_products(products_path)
        return orders.place_order(
            co, args["idempotency_key"], catalog_live
        ).model_dump()

    return {
        "search_products": Tool(
            "search_products",
            "Keyword search over the product catalog.",
            _s(
                "search_products",
                {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "filters": {"type": "object"},
                },
                ["query"],
            ),
            search_products,
        ),
        "get_product": Tool(
            "get_product",
            "Authoritative details for one product.",
            _s("get_product", {"product_id": {"type": "string"}}, ["product_id"]),
            get_product,
        ),
        "search_reviews": Tool(
            "search_reviews",
            "Review evidence for one product.",
            _s(
                "search_reviews",
                {
                    "product_id": {"type": "string"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                ["product_id"],
            ),
            search_reviews,
        ),
        "compare_products": Tool(
            "compare_products",
            "Grounded side-by-side comparison.",
            _s(
                "compare_products",
                {"product_ids": {"type": "array"}},
                ["product_ids"],
            ),
            compare_products,
        ),
        "add_to_cart": Tool(
            "add_to_cart",
            "Add a catalog product to the cart.",
            _s(
                "add_to_cart",
                {"product_id": {"type": "string"}, "quantity": {"type": "integer"}},
                ["product_id"],
            ),
            add_to_cart,
        ),
        "remove_from_cart": Tool(
            "remove_from_cart",
            "Remove a product from the cart.",
            _s(
                "remove_from_cart",
                {"product_id": {"type": "string"}},
                ["product_id"],
            ),
            remove_from_cart,
        ),
        "update_cart_quantity": Tool(
            "update_cart_quantity",
            "Set a cart line quantity (0 removes it).",
            _s(
                "update_cart_quantity",
                {"product_id": {"type": "string"}, "quantity": {"type": "integer"}},
                ["product_id", "quantity"],
            ),
            update_cart_quantity,
        ),
        "get_cart": Tool(
            "get_cart", "Current cart plus totals.", _s("get_cart", {}, []), get_cart
        ),
        "prepare_checkout": Tool(
            "prepare_checkout",
            "Prepare checkout and enter confirmation.",
            _s("prepare_checkout", {}, []),
            prepare_checkout,
        ),
        "confirm_checkout": Tool(
            "confirm_checkout",
            "Confirm the prepared checkout with its token.",
            _s(
                "confirm_checkout",
                {"confirmation_token": {"type": "string"}},
                ["confirmation_token"],
            ),
            confirm_checkout,
        ),
        "place_order": Tool(
            "place_order",
            "Place the order. Requires prior confirmation; idempotent by key.",
            _s(
                "place_order",
                {"idempotency_key": {"type": "string"}},
                ["idempotency_key"],
            ),
            place_order,
        ),
    }
