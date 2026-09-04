"""FastAPI routes. Thin over services; sessions persist per request in SQLite."""
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# ---------------------------------------------------------------------------
# Deterministic chat gates. An order is confirmed only on the order slip (the
# human button or /checkout/confirm) — never in chat, where the model has no
# confirm/place tools. Yet a live model once *narrated* "order confirmed
# 🎉 … email sent" with zero tool calls while the slip sat AWAITING. These
# patterns let the server answer confirm/place wording itself so no model can
# ever describe an order that does not exist.
# ---------------------------------------------------------------------------
_AWAITING_INTENT = re.compile(
    r"("
    r"\b(?:confirm|place|complete|finalize)\b[^\n]{0,60}?"
    r"\b(?:order|checkout|purchase|transaction|payment|it)\b"
    r"|\b(?:proceed|go)\b[^\n]{0,60}?"
    r"\b(?:order|checkout|purchase|transaction|payment)\b"
    r"|\b(?:order|buy|pay)\b[^\n]{0,40}?\b(?:it|now|these|this|them|please)\b"
    r"|\b(?:i|we|yes|yeah|sure|ok|okay|alright)\b[^.!?\n]{0,50}?"
    r"\b(?:confirm|place|complete|checkout|buy|order)\b"
    r"|\b(?:checkout|confirm|place|complete)\s+(?:please|now)\b"
    r")",
    re.IGNORECASE,
)

_PLACE_INTENT = re.compile(
    r"\b(?:confirm|place|complete|finalize)\b[^\n]{0,60}?"
    r"\b(?:order|checkout|purchase|transaction|payment)\b",
    re.IGNORECASE,
)

_CANCEL_INTENT = re.compile(
    r"(\b(?:cancel|abort|void|drop)\b[^\n]{0,40}?"
    r"\b(?:checkout|order|slip|purchase|transaction)\b"
    r"|\b(?:cancel|abort|void)\s+(?:it|this|that|please|now)\b"
    r"|\b(?:cancel|abort|void)\s*[.!?]?$)",
    re.IGNORECASE,
)

_QUESTION_PREFIX = re.compile(
    r"^\s*(?:can|could|may|should|would|do|does|did|is|are|how|what|when|where|why|if)\b",
    re.IGNORECASE,
)

# A catalog/cart turn that answers a product ask with ZERO tool calls is
# ungrounded by construction — a live model once invented five laptops with
# plausible specs under ids that belong to headphones and smartwatches. These
# markers decide when a zero-tool reply must be retried with a search nudge.
_PRODUCT_ASK = re.compile(
    r"(\blaptop\b|\bheadphone\b|\bearbud|\bearphone|\bspeaker\b|\bsmartwatch\b|"
    r"\bwatch\b|\bsmartphone\b|\bphone\b|\btablet\b|\bmonitor\b|\bcamera\b|"
    r"\bkeyboard\b|\bmouse\b|\bshoe\b|\bbackpack\b|\bcoffee\b|\bheadset\b|"
    r"\bscreen\b|\bdisplay\b|\bdrone\b|\bproduct\b|"
    r"\b(?:show|find|need|want|looking for|recommend|best|buy|add|compare)\b|"
    r"under\s+\u20b9?|under\s+rs|rupees|\u20b9)",
    re.IGNORECASE,
)

# The grounding tag belongs to the server, never the model. Live models
# started *echoing* the stored note and one forged it with invented ids —
# strip any such tag from outgoing replies so it can never render or replay.
_PICKS_TAG = re.compile(r"\n?\[Products shown above:[^\]]*\]\n?")

_NO_GROUNDED_FALLBACK = (
    "I couldn't find a grounded answer for that in the catalog. Try "
    "rephrasing (e.g. a category plus a budget), or browse the shop and I'll "
    "help you narrow it down."
)

from app.agent import AgentResult, ShoppingAgent
from app.cart.service import CartError, CartService
from app.catalog.service import ProductNotFound, ProductService, ReviewService
from app.checkout.service import (
    CheckoutService,
    ConfirmationError,
    OrderNotFound,
    OrderService,
    SessionNotFound,
    SqliteOrderStore,
    StaleCheckoutError,
)
from app.config import Settings, load_env_file
from app.llm import LLMError, OpenAICompatibleClient
from app.observe import TraceRecorder
from app.retrieval.corpus import load_products, load_reviews
from app.retrieval.factory import build_search_index
from app.roles import classify, subset_tools
from app.state.models import ConfirmationStatus, Order, ShoppingSession
from app.state.sqlite_store import SqliteStore
from app.tools import build_tools

DomainError = (CartError, ConfirmationError, StaleCheckoutError, ValueError)
SessionMissing = (SessionNotFound, FileNotFoundError)
OrderMissing = (OrderNotFound, KeyError)


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)


class CartAddIn(BaseModel):
    session_id: str | None = None
    product_id: str = ""
    quantity: int = Field(default=1, ge=1, le=99)


class SessionIn(BaseModel):
    session_id: str | None = None


class UpdateIn(BaseModel):
    session_id: str | None = None
    quantity: int = Field(default=1, ge=0, le=99)


class ConfirmIn(BaseModel):
    session_id: str | None = None
    confirmation_token: str = ""


class OrderIn(BaseModel):
    session_id: str | None = None
    idempotency_key: str = Field(default="", max_length=128)


def create_app(settings: Settings | None = None, llm=None) -> FastAPI:
    if settings is None:
        load_env_file()  # local .env convenience for `uvicorn ... --factory`
        settings = Settings.from_env()
    from app.catalog.store import SqliteCatalogStore

    catalog_store = SqliteCatalogStore(
        settings.db_path,
        products_seed=settings.products_path,
        reviews_seed=settings.reviews_path,
    )
    products = catalog_store.list_products()
    catalog = ProductService(products)
    carts = CartService(catalog)

    def _with_names(items) -> list[dict]:
        """Attach catalog names to line items so slips read as a real receipt."""
        named = []
        for it in items or []:
            d = dict(it) if isinstance(it, dict) else it.model_dump()
            pid = d.get("product_id")
            try:
                d["name"] = catalog_store.get_product(pid).name
            except ProductNotFound:
                d["name"] = pid
            named.append(d)
        return named

    def _name_items(payload: dict) -> dict:
        snap = payload.get("cart_snapshot")
        if isinstance(snap, dict):
            snap["items"] = _with_names(snap.get("items", []))
        if isinstance(payload.get("items"), list):
            payload["items"] = _with_names(payload["items"])
        # add_to_cart / update / remove return {"cart": {...}, "totals": {...}};
        # normalize so the client can always read top-level items/totals.
        cart = payload.get("cart")
        if isinstance(cart, dict) and isinstance(cart.get("items"), list):
            cart["items"] = _with_names(cart.get("items", []))
            payload["items"] = cart["items"]
            if "totals" not in payload and "totals" in cart:
                payload["totals"] = payload.get("totals", cart.get("totals"))
        return payload
    checkout = CheckoutService(carts)
    db = SqliteStore(settings.db_path)
    orders = OrderService(catalog, store=SqliteOrderStore(db), catalog_store=catalog_store)
    index = build_search_index(
        products,
        variant=settings.retrieval_variant,
        embedding_model=settings.embedding_model,
        rerank_model=settings.rerank_model,
        rerank_enabled=settings.rerank_enabled,
        hybrid_rrf_k=settings.hybrid_rrf_k,
        rerank_top_n=settings.rerank_top_n,
    )
    tools = build_tools(index, catalog, carts, checkout, orders,
                        catalog_store=catalog_store)
    traces = TraceRecorder(db)
    if llm is None and settings.has_llm():
        llm = OpenAICompatibleClient.from_settings(settings)

    app = FastAPI(title="shop-pilot")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/shop")
    def shop():
        return FileResponse(str(STATIC_DIR / "shop.html"))

    @app.get("/health")
    def health():
        return {"ok": True, "llm": settings.llm_provider if settings.has_llm() else "none"}

    @app.post("/sessions")
    def create_session():
        session = ShoppingSession(session_id=f"S-{uuid.uuid4().hex[:12]}")
        db.save(session)
        return {"session_id": session.session_id}

    def session_of(session_id: str | None) -> ShoppingSession:
        if session_id:
            try:
                return db.load(session_id)
            except SessionMissing:
                raise HTTPException(404, "unknown session") from None
        session = ShoppingSession(session_id=f"S-{uuid.uuid4().hex[:12]}")
        db.save(session)
        return session

    def ctx_of(session: ShoppingSession) -> dict:
        return {"cart": session.cart, "checkout": session.checkout,
                "session_id": session.session_id}

    def persist(session: ShoppingSession, ctx: dict, order: dict | None = None) -> dict:
        session.checkout = ctx.get("checkout")
        if order is not None:
            session.order = Order.model_validate(order)
        db.save(session)
        return {"session_id": session.session_id}

    def _code_safe(text: str, session: ShoppingSession) -> str:
        """Strip the session's confirmation code out of text that will reach
        the model or the stored history. The shopper may paste their slip code
        into chat; the code belongs on the slip, never in the conversation."""
        co = session.checkout
        token = (co.confirmation_token or "") if co is not None else ""
        return text.replace(token, "[confirmation code]") if token else text

    @app.post("/chat")
    def chat(body: ChatIn):
        if llm is None:
            raise HTTPException(
                503,
                "LLM not configured; set LLM_PROVIDER/LLM_BASE_URL/LLM_API_KEY/LLM_MODEL",
            )
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        standing = ctx.get("checkout")
        # Deterministic gate: an order is confirmed only on the slip (the
        # human button or /checkout/confirm), never by chat. If the shopper
        # pastes the standing slip's code into chat, answer without the LLM so
        # no model can ever claim, guess, repeat, or "confirm" anything.
        if (
            standing is not None
            and standing.status == ConfirmationStatus.AWAITING_CONFIRMATION
            and standing.confirmation_token
            and standing.confirmation_token in body.message
        ):
            reply = (
                "I can't confirm that from chat — confirmation happens only "
                "when you press \u201cI confirm this order\u201d on the order slip. "
                "Your code is already on the slip, nothing has been charged, "
                "and no order exists yet. Press the button on the slip (or "
                "Cancel checkout to void it)."
            )
            stored = _code_safe(body.message, session)
            session.messages.append({"role": "user", "content": stored[:4000]})
            session.messages.append({"role": "assistant", "content": reply})
            del session.messages[:-32]
            persist(session, ctx)
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "ok", "role": "cart",
                                   "tool_calls": 0,
                                   "note": "code-paste short-circuit"})
            return {"session_id": session.session_id, "reply": reply,
                    "status": "ok", "steps": 0, "tool_calls": 0,
                    "role": "cart", "tools": [], "products": []}
        # Gate 3 (runs BEFORE the confirm gate): cancel/void wording. A live
        # model once answered "cancel the checkout" by calling clear_cart —
        # emptying the trolley the shopper only wanted to stop checking out.
        # Cancelling voids the slip and NEVER touches the cart, so the server
        # does it directly. Ordering matters: the confirm gate's affirmative
        # pattern ("alright … checkout") once swallowed "alright, cancel the
        # checkout" and answered with the confirm text, doing nothing.
        awaiting = (
            standing is not None
            and standing.status == ConfirmationStatus.AWAITING_CONFIRMATION
        )
        cancel_hit = _CANCEL_INTENT.search(body.message)
        if cancel_hit and not _QUESTION_PREFIX.match(body.message) and "?" not in body.message:
            if awaiting:
                try:
                    checkout.cancel(ctx["checkout"])
                except DomainError:
                    pass
                reply = (
                    "Checkout cancelled — nothing was charged and no order "
                    "was placed. Your trolley is untouched, so you can prepare "
                    "checkout again whenever you're ready."
                )
            else:
                reply = (
                    "There's no checkout to cancel — nothing has been prepared "
                    "or charged, and chat can't cancel placed orders. Your "
                    "trolley is untouched."
                )
            stored = _code_safe(body.message, session)
            session.messages.append({"role": "user", "content": stored[:4000]})
            session.messages.append({"role": "assistant", "content": reply})
            del session.messages[:-32]
            persist(session, ctx)
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "ok", "role": "cart",
                                   "tool_calls": 0,
                                   "note": "cancel-intent short-circuit"})
            return {"session_id": session.session_id, "reply": reply,
                    "status": "ok", "steps": 0, "tool_calls": 0,
                    "role": "cart", "tools": [], "products": []}
        # Question-form cancel ("can I cancel?") while a slip awaits: answer
        # deterministically too, but do NOT void anything.
        if cancel_hit and awaiting:
            reply = (
                "Your checkout is still awaiting your OK — press \u201cCancel "
                "checkout\u201d on the order slip to void it, or just tell me "
                "\u201ccancel the checkout\u201d. Either way your trolley stays "
                "intact."
            )
            stored = _code_safe(body.message, session)
            session.messages.append({"role": "user", "content": stored[:4000]})
            session.messages.append({"role": "assistant", "content": reply})
            del session.messages[:-32]
            persist(session, ctx)
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "ok", "role": "cart",
                                   "tool_calls": 0,
                                   "note": "cancel-question short-circuit"})
            return {"session_id": session.session_id, "reply": reply,
                    "status": "ok", "steps": 0, "tool_calls": 0,
                    "role": "cart", "tools": [], "products": []}
        # Gate 2: confirmation/checkout intent WITHOUT a pasted code. While a
        # slip is awaiting, any finalize-style message ("confirm the order",
        # "place it", "go ahead", "checkout now", …) resolves to the button;
        # with nothing prepared, explicit place-order wording says to prepare
        # first. Either way the LLM never runs, so it can never claim an
        # order, email, tracking, or delivery that does not exist.
        if (
            standing is not None
            and standing.status == ConfirmationStatus.AWAITING_CONFIRMATION
            and _AWAITING_INTENT.search(body.message)
            and not cancel_hit
        ):
            reply = (
                "I can't confirm an order from chat — confirmation happens only "
                "when you press \u201cI confirm this order\u201d on the order slip. "
                "Nothing has been charged and no order exists yet; the slip is "
                "still awaiting your OK. Press the button on the slip (or "
                "Cancel checkout to void it)."
            )
            stored = _code_safe(body.message, session)
            session.messages.append({"role": "user", "content": stored[:4000]})
            session.messages.append({"role": "assistant", "content": reply})
            del session.messages[:-32]
            persist(session, ctx)
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "ok", "role": "cart",
                                   "tool_calls": 0,
                                   "note": "confirm-intent short-circuit"})
            return {"session_id": session.session_id, "reply": reply,
                    "status": "ok", "steps": 0, "tool_calls": 0,
                    "role": "cart", "tools": [], "products": []}
        if _PLACE_INTENT.search(body.message):
            reply = (
                "Nothing is on the order slip yet — no checkout has been "
                "prepared, nothing has been charged, and no order exists. "
                "Fill the trolley and press \u201cPrepare checkout\u201d to review "
                "what you'd be ordering; confirmation always happens on the "
                "slip, never in chat."
            )
            stored = _code_safe(body.message, session)
            session.messages.append({"role": "user", "content": stored[:4000]})
            session.messages.append({"role": "assistant", "content": reply})
            del session.messages[:-32]
            persist(session, ctx)
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "ok", "role": "cart",
                                   "tool_calls": 0,
                                   "note": "place-intent short-circuit"})
            return {"session_id": session.session_id, "reply": reply,
                    "status": "ok", "steps": 0, "tool_calls": 0,
                    "role": "cart", "tools": [], "products": []}
        message = _code_safe(body.message, session)
        role = classify(message)
        agent = ShoppingAgent(
            llm=llm,
            tools=subset_tools(tools, role),
            system_prompt=role.prompt,
            max_steps=role.max_steps,
            max_tool_calls=role.max_tool_calls,
        )
        try:
            result = agent.run(message, ctx, history=session.messages)
        except LLMError as exc:
            raise HTTPException(502, "LLM error") from exc
        if result.status == "failed" and result.text.startswith("LLM error:"):
            # Map provider failures to 502 without echoing raw provider bodies
            # and without poisoning the replay history with error text.
            # The error kind (never the body) is traced for diagnosis.
            traces.record("chat", {"session_id": session.session_id,
                                   "status": "failed",
                                   "role": role.name,
                                   "tool_calls": result.tool_calls_made,
                                   "error": result.text[:200]})
            raise HTTPException(502, "LLM error")
        # Anti-fabrication guard: a product ask answered with ZERO tool calls
        # can only come from memory or invention (live transcript: "show me
        # laptops under 30000" produced five invented SKUs under ids that
        # belong to headphones/smartwatches). Retry once with an explicit
        # search-first instruction; if the model still won't search, answer
        # deterministically instead of replaying its ungrounded text.
        if (
            result.status == "ok"
            and result.tool_calls_made == 0
            and role.name in ("catalog", "cart")
            and _PRODUCT_ASK.search(message)
        ):
            nudge = (
                f"{message}\n\n[Rule: this is a product request — you must "
                "call search_products (or another tool) and answer only from "
                "its results. Never invent products, ids, specs, or prices "
                "from memory. Search now.]"
            )
            try:
                retry = agent.run(nudge, ctx, history=session.messages)
            except LLMError as exc:
                raise HTTPException(502, "LLM error") from exc
            if retry.status == "ok" and retry.tool_calls_made > 0:
                result = retry
            elif retry.status == "ok" and not retry.text.startswith("LLM error:"):
                result = AgentResult(
                    text=_NO_GROUNDED_FALLBACK,
                    status="ok",
                    steps=result.steps + retry.steps + 1,
                    tool_calls_made=result.tool_calls_made,
                    trace=[],
                )
            else:
                raise HTTPException(502, "LLM error")
        # The grounding tag is server-owned: strip any the model echoed or
        # forged so it never renders in the UI or replays as model speech.
        text = _PICKS_TAG.sub("\n", result.text or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        # remember the plain-language turns so later messages have context;
        # keep the last 16 turns (32 messages) so multi-turn context survives.
        # The stored assistant turn also carries a compact "picks" note
        # (ids grounded in tool results, never prose alone) so a later
        # "compare these three" / "add this one" can map names to exact ids
        # instead of the model guessing P01/P02/P03 in sequence.
        session.messages.append({"role": "user", "content": message[:4000]})
        if text:
            # Assistant speech in history is clean reply text ONLY. The
            # grounding picks ride in a separate user-role context entry so a
            # later "compare these three" can map names to ids, but the model
            # never sees the tag as its own words (which made it echo/forge
            # the format in live replies).
            session.messages.append({"role": "assistant", "content": text[:4000]})
            picks = _trace_products(result.trace, text)
            if picks:
                listed = "; ".join(f"{p['product_id']} = {p['name']}" for p in picks)
                session.messages.append({"role": "user", "content": (
                    "[The previous assistant reply showed the shopper these "
                    "products — reuse these exact ids when they refer back "
                    f"('these', 'this one', 'the three'): {listed}]"
                )[:4000]})
        del session.messages[:-32]
        persist(session, ctx)
        traces.record("chat", {"session_id": session.session_id,
                               "status": result.status,
                               "role": role.name,
                               "tool_calls": result.tool_calls_made})
        return {"session_id": session.session_id, "reply": text,
                "status": result.status, "steps": result.steps,
                "tool_calls": result.tool_calls_made,
                "role": role.name,
                "tools": [t["tool"] for t in result.trace] if result.trace else [],
                "products": _trace_products(result.trace, text)}

    def _trace_products(trace, reply: str = "") -> list[dict]:
        """Cards for what the agent actually recommended.

        1. Products named in the reply (Pxx ids) that were also retrieved win —
           the common case: a broad search narrowed to one pick in prose.
        2. Otherwise the most recent product-bearing tool result is used
           (scanned backward, so a trailing productless call like
           search_reviews falls back to the evidence before it). A raw search
           is capped at its top 3 ranked hits; explicit get/compare picks are
           kept whole. Earlier exploratory searches never leak in.
        Only ids seen in tool results are ever included — never taken from
        prose alone.
        """
        import re as _re

        def _ids_of(res: dict) -> list[str]:
            found: list[str] = []
            if res.get("product_id"):
                found.append(res["product_id"])
            for p in res.get("products", []) or []:
                if isinstance(p, dict) and p.get("product_id"):
                    found.append(p["product_id"])
                elif isinstance(p, str):
                    found.append(p)
            return found

        retrieved: list[str] = []
        per_entry: list[tuple[str, list[str]]] = []
        for entry in trace or []:
            res = entry.get("result")
            if not isinstance(res, dict):
                continue
            ids = _ids_of(res)
            per_entry.append((entry.get("tool", ""), ids))
            retrieved.extend(ids)
        retrieved_set = set(retrieved)
        mentioned = [pid for pid in dict.fromkeys(
            _re.findall(r"\bP\d{2}\b", reply or "")) if pid in retrieved_set]
        if mentioned:
            chosen = mentioned[:6]
        else:
            chosen = []
            for tool, ids in reversed(per_entry):
                if ids:
                    chosen = ids[:3] if tool == "search_products" else ids[:6]
                    break
        cards = []
        for pid in list(dict.fromkeys(chosen))[:6]:
            try:
                cards.append(catalog_store.get_product(pid).model_dump())
            except ProductNotFound:
                continue
        return cards

    @app.post("/search")
    def search(body: dict):
        try:
            raw_filters = body.get("filters", {})
            if raw_filters is not None and not isinstance(raw_filters, dict):
                raise ValueError("filters must be an object")
            top_k = int(body.get("top_k", settings.top_k))
            top_k = max(1, min(top_k, 50))
            return tools["search_products"].run(
                {"query": body.get("query", ""), "top_k": top_k,
                 "filters": raw_filters or {}}, {})
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, "invalid search arguments") from exc
        except (OSError, AttributeError) as exc:
            raise HTTPException(500, "search unavailable") from exc

    def _rebuild_catalog_runtime() -> None:
        """Refresh services + retrieval index after any catalog write."""
        fresh = catalog_store.list_products()
        catalog.refresh(fresh)
        try:
            new_index = build_search_index(
                fresh,
                variant=settings.retrieval_variant,
                embedding_model=settings.embedding_model,
                rerank_model=settings.rerank_model,
                rerank_enabled=settings.rerank_enabled,
                hybrid_rrf_k=settings.hybrid_rrf_k,
                rerank_top_n=settings.rerank_top_n,
            )
            new_tools = build_tools(new_index, catalog, carts, checkout, orders,
                                    catalog_store=catalog_store)
            tools.update(new_tools)
        except Exception:
            pass

    @app.get("/products")
    def list_products():
        try:
            return {"products": [p.model_dump() for p in catalog_store.list_products()]}
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc

    @app.get("/categories")
    def list_categories():
        """Distinct catalog categories with counts — powers browse-the-shelves UI."""
        try:
            return {"categories": catalog_store.category_counts()}
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc

    @app.post("/products", status_code=201)
    def create_product(body: dict):
        from app.models import Product as _Product

        try:
            product = _Product(**body)
        except Exception as exc:
            raise HTTPException(400, f"invalid product: {exc}") from None
        try:
            catalog_store.upsert_product(product)
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc
        _rebuild_catalog_runtime()
        return product.model_dump()

    @app.patch("/products/{product_id}")
    def update_product(product_id: str, body: dict):
        try:
            current = catalog_store.get_product(product_id)
        except ProductNotFound as exc:
            raise HTTPException(404, str(exc)) from None
        try:
            merged = current.model_copy(update={k: v for k, v in body.items() if k != "product_id"})
        except Exception as exc:
            raise HTTPException(400, f"invalid product update: {exc}") from None
        try:
            catalog_store.upsert_product(merged)
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc
        _rebuild_catalog_runtime()
        return merged.model_dump()

    @app.delete("/products/{product_id}")
    def delete_product(product_id: str):
        try:
            ok = catalog_store.delete_product(product_id)
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc
        if not ok:
            raise HTTPException(404, f"unknown product: {product_id}")
        _rebuild_catalog_runtime()
        return {"deleted": product_id}

    @app.post("/products/{product_id}/reviews", status_code=201)
    def create_review(product_id: str, body: dict):
        from app.models import Review as _Review

        try:
            review = _Review(**{**body, "product_id": product_id})
        except Exception as exc:
            raise HTTPException(400, f"invalid review: {exc}") from None
        try:
            catalog_store.get_product(product_id)
            catalog_store.upsert_review(review)
        except ProductNotFound as exc:
            raise HTTPException(404, str(exc)) from None
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc
        _rebuild_catalog_runtime()
        return review.model_dump()

    @app.delete("/reviews/{review_id}")
    def delete_review(review_id: str):
        try:
            ok = catalog_store.delete_review(review_id)
        except OSError as exc:
            raise HTTPException(500, "catalog unavailable") from exc
        if not ok:
            raise HTTPException(404, f"unknown review: {review_id}")
        _rebuild_catalog_runtime()
        return {"deleted": review_id}

    @app.get("/products/{product_id}")
    def product(product_id: str):
        try:
            return catalog_store.get_product(product_id).model_dump()
        except ProductNotFound as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/products/{product_id}/reviews")
    def product_reviews(product_id: str, query: str | None = None, top_k: int = 5):
        try:
            top_k = max(0, min(int(top_k), 20))
        except (TypeError, ValueError):
            top_k = 5
        try:
            reviews = ReviewService(catalog_store.list_reviews())
            return {"reviews": reviews.search_reviews(product_id, query, top_k)}
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "reviews unavailable") from exc

    @app.get("/cart")
    def get_cart(session_id: str | None = None):
        # Do not mint junk sessions on anonymous reads without an id.
        if not session_id:
            raise HTTPException(400, "session_id is required")
        session = session_of(session_id)
        return _name_items({"session_id": session.session_id,
                            **tools["get_cart"].run({}, ctx_of(session))})

    @app.post("/cart/items")
    def add_item(body: CartAddIn):
        if not body.product_id:
            raise HTTPException(400, "product_id is required")
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        try:
            out = tools["add_to_cart"].run(
                {"product_id": body.product_id, "quantity": body.quantity}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.patch("/cart/items/{product_id}")
    def update_item(product_id: str, body: UpdateIn):
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        try:
            out = tools["update_cart_quantity"].run(
                {"product_id": product_id, "quantity": body.quantity}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.delete("/cart/items/{product_id}")
    def remove_item(product_id: str, session_id: str | None = None):
        session = session_of(session_id)
        ctx = ctx_of(session)
        try:
            out = tools["remove_from_cart"].run({"product_id": product_id}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.delete("/cart")
    def clear_cart(session_id: str | None = None):
        """Empty the whole trolley at once (mirrors the clear_cart tool)."""
        session = session_of(session_id)
        ctx = ctx_of(session)
        try:
            out = tools["clear_cart"].run({}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.post("/checkout/prepare")
    def prepare(body: SessionIn):
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        try:
            out = tools["prepare_checkout"].run({}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.get("/checkout")
    def show_checkout(session_id: str | None = None):
        session = session_of(session_id)
        if session.checkout is None:
            raise HTTPException(400, "no checkout prepared")
        return _name_items(
            {"session_id": session.session_id, **session.checkout.model_dump()}
        )

    @app.post("/checkout/confirm")
    def confirm(body: ConfirmIn):
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        try:
            out = tools["confirm_checkout"].run(
                {"confirmation_token": body.confirmation_token}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return _name_items({**persist(session, ctx), **out})

    @app.post("/checkout/cancel")
    def cancel(body: SessionIn):
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        if ctx.get("checkout") is None:
            raise HTTPException(400, "no checkout prepared")
        try:
            checkout.cancel(ctx["checkout"])
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        return persist(session, ctx) | {"status": ctx["checkout"].status.value}

    @app.post("/orders")
    def place(body: OrderIn):
        if not body.idempotency_key:
            raise HTTPException(400, "idempotency_key is required")
        session = session_of(body.session_id)
        ctx = ctx_of(session)
        try:
            out = tools["place_order"].run({"idempotency_key": body.idempotency_key}, ctx)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from None
        except (OSError, KeyError) as exc:
            raise HTTPException(500, "order unavailable") from exc
        carts.clear_cart(ctx["cart"])  # purchased lines leave the trolley
        _rebuild_catalog_runtime()  # stock changed: refresh services + index
        return _name_items({**persist(session, ctx, order=out), **out})

    @app.get("/orders/{order_id}")
    def get_order(order_id: str):
        try:
            return _name_items(db.get_order(order_id).model_dump())
        except OrderMissing as exc:
            raise HTTPException(404, "unknown order") from exc

    return app
