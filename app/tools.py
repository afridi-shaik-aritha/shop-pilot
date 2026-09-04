"""Tool registry. Each tool has a JSON schema and a pure function over (args, ctx).

ctx carries the mutable session objects for the current run:
{"cart": Cart, "checkout": Checkout | None}. Tools never touch the LLM.
"""
from dataclasses import dataclass
from typing import Any, Callable

from app.cart.service import CartService
from app.catalog.service import ProductNotFound, ProductService, ReviewService
from app.checkout.service import CheckoutService, OrderService
from app.policy import PolicyService, load_policies
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products, load_reviews
from app.state.models import Cart, ConfirmationStatus


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


def _cart_matches_snapshot(cart: Cart, snapshot: Cart) -> bool:
    """True when the live cart is the exact trolley the slip was cut for."""
    if (cart.currency or "") != (snapshot.currency or ""):
        return False
    if len(cart.items) != len(snapshot.items):
        return False

    def key(i):
        return (i.product_id, i.quantity, round(i.unit_price, 2))

    return sorted(map(key, cart.items)) == sorted(map(key, snapshot.items))


def _drop_stale_slip(ctx: dict) -> None:
    """A pending slip belongs to the exact trolley it was cut for. If the cart
    just changed underneath it, the slip no longer applies — drop it so a
    shopper can never confirm an order for lines they no longer see."""
    co = ctx.get("checkout")
    if (
        co is not None
        and co.status == ConfirmationStatus.AWAITING_CONFIRMATION
        and not _cart_matches_snapshot(_cart_of(ctx), co.cart_snapshot)
    ):
        ctx["checkout"] = None


def _resolve_product_id(args: dict, catalog: ProductService) -> str:
    """Turn a tool call's product reference into a canonical product id.

    Accepts product_id (preferred — exact lookup) or product_name. A wrong
    or model-invented id (e.g. a slug like 'sonicwave_x5' instead of P01) is
    retried as a name so a guessed id can never brick the cart. Ambiguous or
    unmatched references raise with candidate ids the model can retry with.
    """
    def _pick(matches: list, ref: str) -> str:
        if not matches:
            raise ValueError(
                f"no product matches {ref!r} — copy the exact product_id from "
                "search results (e.g. P01) or pass product_name instead"
            )
        if len(matches) > 1:
            listing = "; ".join(f"{m.name} ({m.product_id})" for m in matches)
            raise ValueError(
                f"{ref!r} matches several products: {listing}. Pick the exact product_id."
            )
        return matches[0].product_id

    pid = args.get("product_id")
    if pid:
        try:
            catalog.get_product(pid)
            return pid
        except ProductNotFound:
            return _pick(catalog.find_by_name(pid), pid)
    name = args.get("product_name")
    if not name:
        raise ValueError(
            "provide product_id (copy it from search results, e.g. P01) or product_name"
        )
    return _pick(catalog.find_by_name(name), name)


def build_tools(
    index: ProductIndex,
    catalog: ProductService,
    carts: CartService,
    checkout: CheckoutService,
    orders: OrderService,
    products_path: str = "data/products.json",
    reviews_path: str = "data/reviews.json",
    policies_path: str = "data/policies.json",
    catalog_store=None,
) -> dict[str, Tool]:
    if catalog_store is not None:
        reviews = ReviewService(catalog_store.list_reviews())
    else:
        reviews = ReviewService(load_reviews(reviews_path))

    def search_products(args: dict, ctx: dict) -> dict:
        raw_filters = args.get("filters", {})
        if raw_filters is None:
            raw_filters = {}
        if not isinstance(raw_filters, dict):
            raise ValueError("filters must be an object")
        filters = {k: v for k, v in raw_filters.items()}
        hits = index.search(args["query"], args.get("top_k", 5), filters or None)
        # NOTE: BM25 relevance (r.score) is deliberately NOT exposed — a live
        # model once quoted it as a rating ("4.0/5 (5.71 score)"). The model
        # only needs catalog facts; relevance is a ranking detail.
        return {
            "products": [
                {
                    "product_id": r.product.product_id,
                    "name": r.product.name,
                    "price": r.product.price,
                    "rating": r.product.rating,
                    "category": r.product.category,
                    "brand": r.product.brand,
                    "availability": r.product.availability,
                    "stock": r.product.stock,
                    "review_count": r.product.review_count,
                }
                for r in hits
            ]
        }

    def get_product(args: dict, ctx: dict) -> dict:
        return catalog.get_product(_resolve_product_id(args, catalog)).model_dump()

    def search_reviews(args: dict, ctx: dict) -> dict:
        return {
            "reviews": reviews.search_reviews(
                _resolve_product_id(args, catalog), args.get("query"), args.get("top_k", 5)
            )
        }

    def search_policy(args: dict, ctx: dict) -> dict:
        try:
            rules = PolicyService(load_policies(policies_path)).search(
                args["query"], args.get("top_k", 5)
            )
        except (OSError, ValueError) as exc:
            return {"error": f"policy corpus unavailable: {type(exc).__name__}"}
        return {"rules": rules}

    def compare_products(args: dict, ctx: dict) -> dict:
        ids = [_resolve_product_id({"product_id": i}, catalog) for i in args["product_ids"]]
        return catalog.compare_products(ids)

    def add_to_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.add_to_cart(cart, _resolve_product_id(args, catalog), args.get("quantity", 1))
        _drop_stale_slip(ctx)
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def remove_from_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.remove_from_cart(cart, _resolve_product_id(args, catalog))
        _drop_stale_slip(ctx)
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def update_cart_quantity(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.update_quantity(cart, _resolve_product_id(args, catalog), args["quantity"])
        _drop_stale_slip(ctx)
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def get_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        return {**cart.model_dump(), "totals": carts.totals(cart)}

    def clear_cart(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        carts.clear_cart(cart)
        _drop_stale_slip(ctx)
        return {"cart": cart.model_dump(), "totals": carts.totals(cart)}

    def prepare_checkout(args: dict, ctx: dict) -> dict:
        cart = _cart_of(ctx)
        standing = ctx.get("checkout")
        # Re-preparing the same trolley is a no-op: the standing slip (and its
        # confirmation code) stays valid. A confused model, a double tap, or a
        # shopper asking to "confirm" in chat can then never rotate the slip
        # out from under the shopper or orphan the code on screen. A changed
        # cart or a cancelled/completed slip mints a fresh one.
        if (
            standing is not None
            and standing.status
            in (ConfirmationStatus.AWAITING_CONFIRMATION, ConfirmationStatus.CONFIRMED)
            and _cart_matches_snapshot(cart, standing.cart_snapshot)
        ):
            return standing.model_dump()
        co = checkout.prepare(cart)
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
        if catalog_store is not None:
            try:
                catalog_live = catalog_store.list_products()
            except (OSError, ValueError) as exc:
                raise ValueError(f"catalog unavailable: {type(exc).__name__}") from exc
        else:
            try:
                catalog_live = load_products(products_path)
            except (OSError, ValueError) as exc:
                raise ValueError(f"catalog unavailable: {type(exc).__name__}") from exc
        return orders.place_order(
            co, args["idempotency_key"], catalog_live,
            session_id=ctx.get("session_id"),
        ).model_dump()

    return {
        "search_products": Tool(
            "search_products",
            "Full-text product search — no id or model name is needed; the "
            "query takes the shopper's own words for any attribute: budget, "
            "battery life, features, sensors, reviews, etc. Examples: "
            "'wireless headphones under 10000 with long battery and good "
            "reviews' or 'smartwatch with heart rate tracking'. Optional "
            "filters object: max_price (float, inclusive ceiling in rupees), "
            "category (exact shelf name, e.g. 'wireless headphones'), "
            "in_stock (true keeps in-stock only).",
            _s(
                "search_products",
                {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "filters": {
                        "type": "object",
                        "description": "Optional narrowing filters",
                        "properties": {
                            "max_price": {
                                "type": "number",
                                "description": "Inclusive price ceiling in rupees",
                            },
                            "category": {
                                "type": "string",
                                "description": "Exact catalog category name",
                            },
                            "in_stock": {
                                "type": "boolean",
                                "description": "True keeps availability + stock > 0 only",
                            },
                        },
                    },
                },
                ["query"],
            ),
            search_products,
        ),
        "search_policy": Tool(
            "search_policy",
            "Authoritative store policy rules (shipping, tax, confirmation, returns, payments).",
            _s(
                "search_policy",
                {"query": {"type": "string"}, "top_k": {"type": "integer"}},
                ["query"],
            ),
            search_policy,
        ),
        "get_product": Tool(
            "get_product",
            "Authoritative details for one product. Pass the product_id from "
            "search results (e.g. P01), or product_name if you only know the name.",
            _s(
                "get_product",
                {
                    "product_id": {
                        "type": "string",
                        "description": "Canonical id from search results, e.g. P01",
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Product name, if the id is not known",
                    },
                },
                [],
            ),
            get_product,
        ),
        "search_reviews": Tool(
            "search_reviews",
            "Review evidence for one product (product_id or product_name).",
            _s(
                "search_reviews",
                {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                [],
            ),
            search_reviews,
        ),
        "compare_products": Tool(
            "compare_products",
            "Grounded side-by-side comparison. Accepts product ids (P01) or "
            "names.",
            _s(
                "compare_products",
                {
                    "product_ids": {
                        "type": "array",
                        "description": "Canonical ids from search results (e.g. \"P01\") or "
                        "product names (e.g. \"SonicWave X5 Wireless Headphones\")",
                    }
                },
                ["product_ids"],
            ),
            compare_products,
        ),
        "add_to_cart": Tool(
            "add_to_cart",
            "Add a catalog product to the cart. Pass product_id from search "
            "results (e.g. P01), or product_name if you only know the name.",
            _s(
                "add_to_cart",
                {
                    "product_id": {
                        "type": "string",
                        "description": "Canonical id from search results, e.g. P01",
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Product name as the shopper said it, if the id is not known",
                    },
                    "quantity": {"type": "integer"},
                },
                [],
            ),
            add_to_cart,
        ),
        "remove_from_cart": Tool(
            "remove_from_cart",
            "Remove a product from the cart (product_id or product_name).",
            _s(
                "remove_from_cart",
                {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                },
                [],
            ),
            remove_from_cart,
        ),
        "update_cart_quantity": Tool(
            "update_cart_quantity",
            "Set a cart line quantity (0 removes it). product_id or "
            "product_name identifies the line.",
            _s(
                "update_cart_quantity",
                {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                ["quantity"],
            ),
            update_cart_quantity,
        ),
        "get_cart": Tool(
            "get_cart", "Current cart plus totals.", _s("get_cart", {}, []), get_cart
        ),
        "clear_cart": Tool(
            "clear_cart",
            "Empty the whole trolley — removes every line at once. Use when "
            "the shopper says clear/empty the cart, remove everything, or "
            "start over. (To change a single line instead, use "
            "update_cart_quantity with 0 or remove_from_cart.)",
            _s("clear_cart", {}, []),
            clear_cart,
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
