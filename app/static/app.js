/* Shop-Pilot web app. Zero-dependency vanilla JS module. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const LS_KEY = "shopPilot.session";
const CHAT_KEY = "shopPilot.chat";
const LS_ORDER_KEY = "shopPilot.lastOrder";

const state = {
  sessionId: localStorage.getItem(LS_KEY) || null,
  llmMode: "unknown", // unknown | on | off
  busy: false,
  cart: null,
  checkout: null,
  order: null,
  lastOrder: null,
  mock: false,
};

const els = {
  messages: $("#messages"),
  input: $("#input"),
  form: $("#composerForm"),
  send: $("#send"),
  badge: $("#llmBadge"),
  cartBody: $("#cartBody"),
  cartCount: $("#cartCount"),
  checkoutBody: $("#checkoutBody"),
  modalRoot: $("#modalRoot"),
  toast: $("#toast"),
};

/* ---------- tiny helpers ---------- */
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

const inr = (n) => {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return "₹" + v.toLocaleString("en-IN", {
    minimumFractionDigits: v % 1 ? 2 : 0,
    maximumFractionDigits: 2,
  });
};

const uid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + Math.random().toString(16).slice(2));

function toast(msg, kind = "") {
  els.toast.hidden = false;
  els.toast.className = "toast " + kind;
  els.toast.innerHTML = `<span>${esc(msg)}</span><button class="toast-x" aria-label="dismiss">&times;</button>`;
  const t = setTimeout(() => { els.toast.hidden = true; }, 4200);
  $(".toast-x", els.toast).onclick = () => { clearTimeout(t); els.toast.hidden = true; };
}

/* ---------- persistence: chat transcript + last order ---------- */
function persistChat() {
  try { localStorage.setItem(CHAT_KEY, els.messages.innerHTML); } catch { /* private mode */ }
}
function clearChat() {
  try { localStorage.removeItem(CHAT_KEY); } catch {}
}
function saveLastOrder(order) {
  state.lastOrder = order;
  try {
    localStorage.setItem(LS_ORDER_KEY, JSON.stringify({
      order_id: order.order_id, total: order.total, status: order.status, items: order.items,
    }));
  } catch {}
}
function restoreSaved() {
  let chat = null, last = null;
  try { chat = localStorage.getItem(CHAT_KEY); } catch {}
  try { last = localStorage.getItem(LS_ORDER_KEY); } catch {}
  if (last) {
    try {
      const o = JSON.parse(last);
      if (o && o.order_id) state.lastOrder = o;
    } catch {}
  }
  if (!chat || !/<div class="msg/.test(chat)) return;
  // Guard against stale markup from older deploys: only restore the known
  // version marker; otherwise start fresh.
  if (!chat.includes("data-chat-v=\"1\"") && !chat.includes('class="msg')) return;
  els.messages.innerHTML = chat;
  $$(".pc-add", els.messages).forEach((b) => (b.onclick = () => addToCart(b.dataset.id, 1, b.dataset.name)));
  $$(".pc-detail", els.messages).forEach((b) => (b.onclick = () => productModal(b.dataset.id)));
  scrollBottom();
}

/* ---------- API ---------- */
async function api(method, path, body, { timeoutMs = 25000 } = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const opts = { method, headers: {}, signal: ctrl.signal };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const detail = data && typeof data.detail === "string" ? data.detail : res.statusText;
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") {
      const e = new Error("request timed out — the server took too long");
      e.status = 0;
      throw e;
    }
    throw err;
  } finally {
    clearTimeout(t);
  }
}
const get = (p) => api("GET", p);
const post = (p, b) => api("POST", p, b);
const patch = (p, b) => api("PATCH", p, b);
const del = (p) => api("DELETE", p);

function clearSavedSession() {
  state.sessionId = null;
  try { localStorage.removeItem(LS_KEY); } catch {}
}

/* If the stored session is dead server-side (DB wiped/restarted fresh),
   drop the saved transcript + order too: they reference server state
   (cart, slips) that no longer exists. A live session keeps its transcript. */
async function validateStoredSession() {
  if (!state.sessionId || state.mock) return;
  try {
    await get(`/cart?session_id=${encodeURIComponent(state.sessionId)}`);
  } catch (err) {
    if (err && err.status === 404) {
      clearSavedSession();
      clearChat();
      try { localStorage.removeItem(LS_ORDER_KEY); } catch {}
      state.lastOrder = null;
    }
  }
}

async function ensureSession() {
  if (state.sessionId) return state.sessionId;
  // Prefer the explicit session endpoint; fall back to the legacy
  // GET /cart bootstrap for the offline mock and older servers.
  try {
    const data = await post("/sessions", {});
    state.sessionId = data.session_id;
  } catch {
    const data = await get("/cart");
    state.sessionId = data.session_id;
  }
  localStorage.setItem(LS_KEY, state.sessionId);
  return state.sessionId;
}

async function withSessionRecovery(fn) {
  try {
    return await fn();
  } catch (err) {
    if (err && err.status === 404 && state.sessionId) {
      // Server restarted / DB thrown away: drop the dead id once and retry
      // with a fresh session instead of toasting forever.
      clearSavedSession();
      await ensureSession();
      return await fn();
    }
    throw err;
  }
}

/* ---------- chat rendering ---------- */
function mdLite(text) {
  return esc(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function addUserMsg(text) {
  const node = document.createElement("div");
  node.className = "msg user";
  node.innerHTML = `<div class="bubble"><div class="who">you</div><div class="plain">${mdLite(text)}</div></div>`;
  els.messages.appendChild(node);
  scrollBottom();
  persistChat();
  return node;
}

function addAssistantPlaceholder() {
  const node = document.createElement("div");
  node.className = "msg bot";
  node.innerHTML =
    `<div class="bubble"><div class="typing"><span></span><span></span><span></span></div>` +
    `<div class="think-line">hunting the catalog…</div></div>`;
  const lines = ["hunting the catalog…", "reading the reviews…", "adding to your trolley…"];
  let i = 0;
  node._think = setInterval(() => {
    const l = $(".think-line", node);
    if (l) l.textContent = lines[i++ % lines.length];
  }, 1500);
  els.messages.appendChild(node);
  scrollBottom();
  return node;
}

function stopThinking(node) {
  if (node && node._think) { clearInterval(node._think); node._think = null; }
}

function fillAssistant(node, text, tools = []) {
  stopThinking(node);
  const body = $(".bubble", node);
  body.innerHTML =
    `<div class="who">assistant</div>` +
    `<div class="plain">${mdLite(text || "_no reply_")}</div>` +
    (tools.length
      ? `<div class="tool-chips">` + tools.map((t) => `<span class="tool-chip">${esc(t)}</span>`).join("") + `</div>`
      : "");
  scrollBottom();
  persistChat();
}

function addAssistantMsg(text, tools = []) {
  const node = document.createElement("div");
  node.className = "msg bot";
  node.innerHTML = `<div class="bubble"></div>`;
  els.messages.appendChild(node);
  fillAssistant(node, text, tools);
  return node;
}

function addErrorMsg(text) {
  const node = document.createElement("div");
  node.className = "msg bot";
  node.innerHTML = `<div class="bubble err-note"><div class="who" style="color:var(--red)">notice</div><div class="plain">${esc(text)}</div></div>`;
  els.messages.appendChild(node);
  scrollBottom();
  persistChat();
}

function addSearchResults(query, hits) {
  const node = document.createElement("div");
  node.className = "msg bot";
  node.innerHTML =
    `<div class="bubble"><div class="who">catalog · “${esc(query)}”</div><div class="results"></div></div>`;
  els.messages.appendChild(node);
  const grid = $(".results", node);
  grid.innerHTML = hits.map(cardHtml).join("");
  $$(".pc-add", grid).forEach((b) => (b.onclick = () => addToCart(b.dataset.id, 1, b.dataset.name)));
  $$(".pc-detail", grid).forEach((b) => (b.onclick = () => productModal(b.dataset.id)));
  scrollBottom();
  persistChat();
}

/* Product cards under an LLM chat reply, built only from product ids the
   agent actually retrieved (server's `products` array) — never prose parsing.
   This is what makes "tap Add to cart" real in chat mode. */
function addAssistantCards(hits) {
  if (!hits || !hits.length) return;
  const node = document.createElement("div");
  node.className = "msg bot";
  node.innerHTML =
    `<div class="bubble"><div class="who">assistant picks</div><div class="results"></div></div>`;
  els.messages.appendChild(node);
  const grid = $(".results", node);
  grid.innerHTML = hits.map(cardHtml).join("");
  $$(".pc-add", grid).forEach((b) => (b.onclick = () => addToCart(b.dataset.id, 1, b.dataset.name)));
  $$(".pc-detail", grid).forEach((b) => (b.onclick = () => productModal(b.dataset.id)));
  scrollBottom();
  persistChat();
}

/* ---------- product sticker art (deterministic, no images needed) ---------- */
const ART_PALETTE = ["#ffd43b", "#ffb25e", "#ffa07a", "#c8e6b0", "#b3d0f2", "#e3c3ef", "#f7d9a0", "#f2bfbf"];
const ART_ICONS = {
  headphones: `<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13.5" width="4.2" height="6.5" rx="2"/><rect x="16.8" y="13.5" width="4.2" height="6.5" rx="2"/>`,
  speaker: `<rect x="7" y="4" width="10" height="16" rx="2.5"/><circle cx="12" cy="10.5" r="2.4"/><path d="M9.4 16h5.2"/>`,
  watch: `<rect x="7.5" y="4.5" width="9" height="15" rx="2.6"/><path d="M9.6 4.5V2.6h4.8v1.9M9.6 19.5v1.9h4.8v-1.9"/><path d="M10.4 12h1.5l.7-1.8 1.1 2.4"/>`,
  bag: `<path d="M6 8h12l-1.1 10.5a2 2 0 0 1-2 1.7H9.1a2 2 0 0 1-2-1.7L6 8z"/><path d="M9 10.5V7a3 3 0 0 1 6 0v3.5"/>`,
};
function pickArt(p) {
  const cat = String(p.category || "").toLowerCase();
  if (cat.includes("headphone") || cat.includes("earphone") || cat.includes("bud")) return "headphones";
  if (cat.includes("speaker")) return "speaker";
  if (cat.includes("watch")) return "watch";
  return "bag";
}
function artColor(id) {
  let s = 0;
  for (const ch of String(id)) s += ch.charCodeAt(0);
  return ART_PALETTE[s % ART_PALETTE.length];
}
function artHtml(p, cls = "pc-art", size = 26) {
  const color = artColor(p.product_id);
  return `<span class="${cls}" style="background:${color}" aria-hidden="true">` +
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ART_ICONS[pickArt(p)]}</svg></span>`;
}

function cardHtml(p) {
  const stock = p.stock ?? (p.availability === false ? 0 : 1);
  const inStock = p.availability !== false && stock > 0;
  const category = p.category || "catalog";
  const brand = p.brand || "";
  const rating = Number(p.rating);
  const ratingText = Number.isFinite(rating) ? rating.toFixed(1) : "—";
  const stars = Number.isFinite(rating)
    ? "★".repeat(Math.min(5, Math.max(1, Math.floor(rating))))
    : "★";
  return `<div class="product-card">
    <div class="pc-head">
      ${artHtml(p)}
      <div class="pc-head-text">
        <span class="cat">${esc(category)}</span>
        <h4>${esc(p.name)}</h4>
        <div class="brand">${esc(brand)}</div>
      </div>
    </div>
    <div class="price">${inr(p.price)}</div>
    <div class="meta">
      <span class="star">${stars} ${esc(ratingText)}</span>
      <span>${esc(p.review_count ?? 0)} reviews</span>
      <span class="pill ${inStock ? "in" : "out"}">${inStock ? "in stock" : "out of stock"}</span>
    </div>
    <div class="card-actions">
      <button class="btn btn-sm pc-detail" data-id="${esc(p.product_id)}">Details</button>
      <button class="btn btn-sm btn-primary pc-add" data-id="${esc(p.product_id)}" data-name="${esc(p.name || p.product_id)}" ${inStock ? "" : "disabled"}>Add to cart</button>
    </div>
  </div>`;
}

const scrollBottom = () => { els.messages.scrollTop = els.messages.scrollHeight; };

/* ---------- chat flow ---------- */
async function sendMessage(text) {
  const q = (text ?? els.input.value).trim();
  if (!q || state.busy) return;
  if (state.llmMode === "off") { runCatalogSearch(q); return; }
  state.busy = true;
  setBusy(true);
  els.input.value = "";
  hideGreeting();
  addUserMsg(q);
  const placeholder = addAssistantPlaceholder();
  try {
    await ensureSession();
    const data = await withSessionRecovery(() =>
      post("/chat", { session_id: state.sessionId, message: q }));
    if (data.status === "failed") {
      fillAssistant(placeholder, data.reply, data.tools || []);
      toast("The model run ended without success.", "err");
    } else {
      fillAssistant(placeholder, data.reply, data.tools || []);
      addAssistantCards(data.products);
    }
    await refreshCart();
  } catch (err) {
    stopThinking(placeholder);
    placeholder.remove();
    if (err.status === 503) {
      state.llmMode = "off";
      renderBadge();
      addErrorMsg("No LLM is configured on this server. Searching the catalog directly instead — try the chips below.");
    } else if (err && err.status === 404) {
      clearSavedSession();
      addErrorMsg("Session expired — started fresh. Please send your message again.");
    } else {
      addErrorMsg("Request failed: " + err.message);
    }
  } finally {
    state.busy = false;
    setBusy(false);
    els.input.focus();
  }
}

/* catalog-only search (no LLM required) */
async function runCatalogSearch(query) {
  if (state.busy) return;
  state.busy = true; setBusy(true);
  hideGreeting();
  addUserMsg(query);
  els.input.value = "";
  const ph = addAssistantPlaceholder();
  try {
    const data = await withSessionRecovery(async () => {
      await ensureSession();
      return await post("/search", { query, top_k: 6, filters: {} });
    });
    stopThinking(ph);
    ph.remove();
    if (data.products && data.products.length) addSearchResults(query, data.products);
    else addAssistantMsg("Nothing matched that query in the catalog. Try another wording.");
  } catch (err) {
    stopThinking(ph);
    ph.remove();
    if (err && err.status === 404 && state.sessionId) {
      clearSavedSession();
      addErrorMsg("Session expired — started a fresh one. Please retry your search.");
    } else {
      addErrorMsg("Search failed: " + err.message);
    }
  } finally {
    state.busy = false; setBusy(false);
  }
}

function setBusy(b) {
  els.send.disabled = b;
  els.input.disabled = b;
}

/* ---------- cart ---------- */
function normalizeCartPayload(data) {
  // Accept every shape the API/mock has ever returned:
  // {items, totals} | {cart:{items}, totals} | {cart, ...}
  if (!data) return data;
  if (Array.isArray(data.items)) return data;
  if (data.cart && Array.isArray(data.cart.items)) {
    return { ...data, items: data.cart.items, totals: data.totals || data.cart.totals };
  }
  return data;
}

function voidStaleSlip(reason) {
  if (state.checkout && state.checkout.status === "AWAITING_CONFIRMATION") {
    state.checkout = null;
    renderCheckout();
    if (reason) toast(reason);
  }
}

async function refreshCart() {
  try {
    await ensureSession();
    const raw = await withSessionRecovery(() =>
      get(`/cart?session_id=${encodeURIComponent(state.sessionId)}`));
    state.cart = normalizeCartPayload(raw);
    renderCart();
    await refreshCheckoutView();
  } catch (err) {
    if (err && err.status === 404) {
      clearSavedSession();
      toast("Session expired — starting fresh. Please retry.", "err");
    } else {
      toast("Could not refresh cart: " + err.message, "err");
    }
  }
}

function renderCart() {
  const items = state.cart?.items || [];
  const totals = state.cart?.totals || null;
  const awaiting = state.checkout && state.checkout.status === "AWAITING_CONFIRMATION" && !state.order;
  els.cartCount.hidden = items.length === 0;
  els.cartCount.textContent = items.reduce((n, i) => n + i.quantity, 0);
  if (!items.length) {
    els.cartBody.className = "panel-body empty";
    els.cartBody.textContent = "Empty for now. Ask the assistant to add the good stuff, or pick from a search.";
    return;
  }
  els.cartBody.className = "panel-body";
  els.cartBody.innerHTML =
    items.map(
      (i) => `<div class="cart-item">
        <div>
          <div class="ci-name">${esc(i.name || i.product_id)}</div>
          <div class="ci-price">${inr(i.unit_price)} each</div>
        </div>
        <div class="ci-right">
          <div class="qty">
            <button data-act="dec" data-id="${esc(i.product_id)}" aria-label="Decrease quantity of ${esc(i.name || i.product_id)}">−</button>
            <span>${i.quantity}</span>
            <button data-act="inc" data-id="${esc(i.product_id)}" aria-label="Increase quantity of ${esc(i.name || i.product_id)}">+</button>
          </div>
          <button class="icon-btn" data-act="rm" data-id="${esc(i.product_id)}" aria-label="Remove ${esc(i.name || i.product_id)} from cart">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 7h16M9 7V5h6v2m-8 0l1 13h8l1-13"/></svg>
          </button>
        </div>
      </div>`
    ).join("") +
    `<div class="totals">
      <div class="row"><span>Subtotal</span><span>${inr(totals?.subtotal)}</span></div>
      <div class="row"><span>Shipping</span><span>${inr(totals?.shipping)}</span></div>
      <div class="row"><span>GST (18%)</span><span>${inr(totals?.tax)}</span></div>
      <div class="row grand"><span>Total</span><span class="amt">${inr(totals?.total)}</span></div>
    </div>
    <div class="panel-actions">
      <button class="btn btn-primary btn-block" id="prepareBtn" ${awaiting ? "disabled" : ""} title="${awaiting ? "Review the slip and confirm or cancel it first" : ""}">${awaiting ? "On the slip — awaiting your OK" : "Prepare checkout"}</button>
    </div>`;
  $$("[data-act]", els.cartBody).forEach((b) =>
    (b.onclick = () => cartAction(b.dataset.act, b.dataset.id)));
  $("#prepareBtn", els.cartBody).onclick = prepareCheckout;
}

async function cartAction(act, productId) {
  try {
    await ensureSession();
    const sid = state.sessionId;
    const doMutate = async () => {
      if (act === "inc") await patch(`/cart/items/${productId}`, { session_id: sid, quantity: currentQty(productId) + 1 });
      else if (act === "dec") await patch(`/cart/items/${productId}`, { session_id: sid, quantity: Math.max(0, currentQty(productId) - 1) });
      else if (act === "rm") await del(`/cart/items/${productId}?session_id=${encodeURIComponent(sid)}`);
    };
    await withSessionRecovery(doMutate);
    // Any cart mutation voids an awaiting slip server-side (snapshot-bound
    // token); mirror that immediately so the UI never shows a stale token.
    voidStaleSlip("Cart changed — the old slip no longer applies. Hit Prepare again.");
    await refreshCart();
  } catch (err) { toast("Cart update failed: " + err.message, "err"); }
}
const currentQty = (pid) => (state.cart?.items || []).find((i) => i.product_id === pid)?.quantity || 0;

async function addToCart(productId, quantity = 1, productName = null) {
  try {
    await ensureSession();
    const sid = state.sessionId;
    const data = await withSessionRecovery(() =>
      post("/cart/items", { session_id: sid, product_id: productId, quantity }));
    state.cart = normalizeCartPayload(data);
    renderCart();
    voidStaleSlip("Cart changed — the old slip no longer applies. Hit Prepare again.");
    const label = productName
      || (state.cart?.items || []).find((i) => i.product_id === productId)?.name
      || productId;
    toast(`${label} added to cart`);
  } catch (err) { toast("Could not add: " + err.message, "err"); }
}

/* ---------- checkout ---------- */
async function prepareCheckout() {
  try {
    await ensureSession();
    state.checkout = await post("/checkout/prepare", { session_id: state.sessionId });
    state.checkout.confirmed = false;
    renderCheckout();
    renderCart(); // gate the Prepare button while a slip is awaiting confirmation
    toast("On the slip — give it a once-over, then confirm.");
  } catch (err) { toast("Could not prepare checkout: " + err.message, "err"); }
}

function renderCheckout() {
  const co = state.checkout;
  if (!co || !co.checkout_id) {
    if (state.lastOrder) {
      els.checkoutBody.className = "panel-body";
      els.checkoutBody.innerHTML = recapHtml(state.lastOrder);
      $("#startFresh", els.checkoutBody)?.addEventListener("click", newSession);
    } else {
      els.checkoutBody.className = "panel-body empty";
      els.checkoutBody.textContent = "Nothing on the slip yet. Fill the trolley, then hit Prepare checkout to review what you'd be ordering.";
    }
    return;
  }
  els.checkoutBody.className = "panel-body";
  const awaiting = co.status === "AWAITING_CONFIRMATION" && !state.order;
  const completed = co.status === "COMPLETED" && !state.order;
  const items = co.cart_snapshot?.items || [];
  const orderBanner = state.order
    ? `<div class="order-ok"><div class="stamp" aria-hidden="true"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg></div><h4>Order placed</h4>
       <p>${esc(state.order.order_id)} · ${inr(state.order.total)} · ${esc(state.order.status)}</p>
       <p style="font-size:11.5px;color:var(--text-2)">Placed only by your explicit confirmation.</p></div>`
    : "";
  els.checkoutBody.innerHTML = `
    ${orderBanner}
    <span class="co-status ${awaiting ? "await" : "done"}">${esc(co.status)}</span>
    ${items.map((i) => `<div class="co-line"><span>${i.quantity}× ${esc(i.name || i.product_id)}</span><span>${inr(i.unit_price * i.quantity)}</span></div>`).join("")}
    <div class="co-line" style="border-top-style:solid"><strong>Total</strong><strong>${inr(co.total)}</strong></div>
    ${awaiting ? tokenHtml(co) : ""}
    <div class="panel-actions">${actionButtons(awaiting, completed)}</div>`;
  if (awaiting) {
    $("#confirmBtn", els.checkoutBody).onclick = confirmOrder;
    $("#cancelBtn", els.checkoutBody).onclick = cancelCheckout;
    $("#copyToken", els.checkoutBody).onclick = () => {
      navigator.clipboard?.writeText(co.confirmation_token);
      toast("Confirmation code copied");
    };
  }
  if (state.order || completed) {
    $("#newOrderBtn", els.checkoutBody)?.addEventListener("click", dismissOrderSlip);
  }
}

function tokenHtml(co) {
  return `<div class="tokenbox">
      <div class="ttl">Your confirmation code</div>
      <div class="tok-row">
        <code aria-label="confirmation code">${esc(co.confirmation_token)}</code>
        <button class="btn btn-sm" id="copyToken" type="button">Copy</button>
      </div>
      <p class="tok-note">No order is placed until you confirm with this code. It belongs to this exact trolley — change the cart and it no longer applies.</p>
    </div>`;
}

function actionButtons(awaiting, completed) {
  if (state.order || completed) {
    return `<button class="btn btn-primary btn-block" id="newOrderBtn">Done</button>`;
  }
  if (!awaiting) return "";
  return `<button class="btn btn-primary btn-block" id="confirmBtn">✓ I confirm this order</button>
      <button class="btn btn-danger btn-block" id="cancelBtn">Cancel checkout</button>`;
}

function dismissOrderSlip() {
  state.order = null;
  state.checkout = null;
  renderCart();
  renderCheckout();
}

function recapHtml(o) {
  const items = (o.items || []).map(
    (i) => `<div class="co-line"><span>${i.quantity}× ${esc(i.name || i.product_id)}</span><span>${inr((i.unit_price || 0) * i.quantity)}</span></div>`
  ).join("");
  return `<div class="recap">
    <div class="order-ok" style="padding:0 0 6px">
      <div class="stamp" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg></div>
      <h4 style="margin:8px 0 2px">That's ordered</h4>
      <p style="margin:0">${esc(o.order_id)} · ${inr(o.total)}</p>
    </div>
    ${items}
    <div class="co-line" style="border-top:1.5px solid var(--line-strong);margin-top:8px;padding-top:8px"><strong>Total</strong><strong>${inr(o.total)}</strong></div>
    <div class="panel-actions">
      <button class="btn btn-ghost btn-block" id="startFresh" type="button">Start a fresh session</button>
    </div>
  </div>`;
}

async function confirmOrder() {
  const co = state.checkout;
  if (!co) return;
  const btn = $("#confirmBtn");
  btn.disabled = true; btn.textContent = "Confirming…";
  try {
    const sid = state.sessionId;
    await withSessionRecovery(() =>
      post("/checkout/confirm", { session_id: sid, confirmation_token: co.confirmation_token }));
    // Reuse one idempotency key per checkout so retries/double-clicks dedupe
    // instead of creating a second order.
    if (!co._orderKey) co._orderKey = "ui-" + uid();
    const order = await withSessionRecovery(() =>
      post("/orders", { session_id: sid, idempotency_key: co._orderKey }));
    saveLastOrder(order);
    state.order = order;
    if (state.checkout) state.checkout.status = "COMPLETED"; // mirror server-side flip
    toast(`Order ${order.order_id} completed`);
    await refreshCart();
    renderCheckout();
  } catch (err) {
    if (err && /stale|cancelled|does not match|no checkout/i.test(err.message || "")) {
      // Server voided the slip (cart changed underneath us): drop it loudly.
      state.checkout = null;
      renderCheckout();
      await refreshCart();
    }
    btn.disabled = false; btn.textContent = "✓ I confirm this order";
    toast("Order failed: " + err.message, "err");
  }
}

async function cancelCheckout() {
  try {
    await ensureSession();
    await post("/checkout/cancel", { session_id: state.sessionId });
    state.checkout = null;
    renderCheckout();
    renderCart(); // re-enable Prepare now that the slip is voided
    toast("Checkout cancelled — nothing was charged.");
  } catch (err) { toast("Cancel failed: " + err.message, "err"); }
}

async function refreshCheckoutView() {
  // Always sync from the server so a cart edit that voided the slip is
  // reflected immediately instead of showing a stale token.
  try {
    await ensureSession();
    const data = await withSessionRecovery(() =>
      get(`/checkout?session_id=${encodeURIComponent(state.sessionId)}`));
    // Preserve the client-side idempotency key across refreshes.
    if (state.checkout && state.checkout._orderKey && data.checkout_id === state.checkout.checkout_id) {
      data._orderKey = state.checkout._orderKey;
    }
    state.checkout = data;
  } catch {
    state.checkout = null;
  }
  renderCheckout();
}

/* ---------- product modal ---------- */
async function productModal(productId) {
  try {
    const p = await withSessionRecovery(() => get(`/products/${productId}`));
    const stock = p.stock ?? (p.availability === false ? 0 : 1);
    const inStock = p.availability !== false && stock > 0;
    const rating = Number(p.rating);
    const ratingText = Number.isFinite(rating) ? rating.toFixed(1) : "—";
    els.modalRoot.innerHTML = `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-label="${esc(p.name)}">
      <button class="btn btn-ghost m-close" aria-label="Close product details">&times;</button>
      <div class="modal-top">
        ${artHtml(p, "pc-art m-art", 34)}
        <div>
          <div class="cat">${esc(p.category || "catalog")}</div>
          <h3>${esc(p.name)}</h3>
          <div class="brand-sub">by ${esc(p.brand || "")} · ${esc(p.product_id)}</div>
        </div>
      </div>
      <div class="m-hero">
        <div class="m-price">${inr(p.price)}</div>
        <div class="m-stats">
          <span class="stat star">★ ${esc(ratingText)}</span>
          <span class="stat">${esc(p.review_count ?? 0)} reviews</span>
          <span class="stat ${inStock ? "" : ""}" style="color:${inStock ? "var(--ok)" : "var(--err)"}">${inStock ? "in stock" : "out of stock"}</span>
        </div>
      </div>
      <div class="desc">${esc(p.description)}</div>
      <div class="tabs" role="tablist" aria-label="Product information">
        <button class="tab on" id="tabSpecs" role="tab" aria-selected="true">Specifications</button>
        <button class="tab" id="tabReviews" role="tab" aria-selected="false">Reviews</button>
      </div>
      <div id="modalContent" role="tabpanel"></div>
      <div class="panel-actions">
        <button class="btn btn-primary btn-block" id="mAdd" aria-label="Add ${esc(p.name || productId)} to cart" ${inStock ? "" : "disabled"}>Add to cart · ${inr(p.price)}</button>
      </div>
    </div></div>`;

    const prevFocus = document.activeElement;
    const onKey = (e) => {
      if (e.key === "Escape") { close(); return; }
      if (e.key === "Tab") {
        // Simple focus trap: keep tab cycling inside the dialog.
        const focusables = $$('button, [href], input, [tabindex]:not([tabindex="-1"])', els.modalRoot)
          .filter((el) => !el.disabled);
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const tabs = [$("#tabSpecs", els.modalRoot), $("#tabReviews", els.modalRoot)];
        if (tabs.includes(document.activeElement)) {
          e.preventDefault();
          (document.activeElement === tabs[0] ? tabs[1] : tabs[0]).focus();
        }
      }
    };
    const close = () => {
      window.removeEventListener("keydown", onKey);
      els.modalRoot.innerHTML = "";
      if (prevFocus && prevFocus.focus) prevFocus.focus();
    };
    window.addEventListener("keydown", onKey);
    $(".m-close", els.modalRoot).onclick = close;
    $(".modal-backdrop", els.modalRoot).addEventListener("click", (e) => { if (e.target.classList.contains("modal-backdrop")) close(); }, { once: true });
    $("#mAdd", els.modalRoot).onclick = () => { addToCart(p.product_id, 1, p.name); close(); };
    $(".m-close", els.modalRoot).focus();

    const content = $("#modalContent");
    const specsHtml = `<table class="specs">${Object.entries(p.specs || {})
      .map(([k, v]) => `<tr><td>${esc(String(k).replace(/_/g, " "))}</td><td>${esc(v)}</td></tr>`).join("")}</table>`;
    content.innerHTML = specsHtml || "<p class='empty'>No specifications listed.</p>";

    $("#tabSpecs", els.modalRoot).onclick = () => {
      $("#tabSpecs", els.modalRoot).classList.add("on"); $("#tabReviews", els.modalRoot).classList.remove("on");
      $("#tabSpecs", els.modalRoot).setAttribute("aria-selected", "true");
      $("#tabReviews", els.modalRoot).setAttribute("aria-selected", "false");
      content.innerHTML = specsHtml || "<p class='empty'>No specifications listed.</p>";
    };
    $("#tabReviews", els.modalRoot).onclick = async () => {
      $("#tabReviews", els.modalRoot).classList.add("on"); $("#tabSpecs", els.modalRoot).classList.remove("on");
      $("#tabReviews", els.modalRoot).setAttribute("aria-selected", "true");
      $("#tabSpecs", els.modalRoot).setAttribute("aria-selected", "false");
      content.innerHTML = "<p class='empty'>Loading reviews…</p>";
      try {
        const data = await get(`/products/${productId}/reviews`);
        content.innerHTML = (data.reviews || []).length
          ? data.reviews.map((r) => {
              const rr = Number(r.rating);
              const rc = Number.isFinite(rr) ? Math.min(5, Math.max(1, Math.floor(rr))) : 1;
              return `<div class="review">
                <div class="rv-head"><span class="stars">${"★".repeat(rc)}</span>
                <span>${esc(r.rating)}/5</span><span style="color:var(--text-2)">${esc(r.helpful_votes ?? 0)} helpful</span></div>
              <div class="rv-title">${esc(r.title)}</div><div class="rv-body">${esc(r.body)}</div>
            </div>`;}).join("")
          : "<p class='empty'>No reviews yet for this product.</p>";
      } catch (err) { content.innerHTML = `<p class='empty'>Reviews unavailable: ${esc(err.message)}</p>`; }
    };
  } catch (err) { toast("Could not load product: " + err.message, "err"); }
}

/* ---------- boot ---------- */
function renderBadge() {
  const b = els.badge;
  const suffix = state.mock ? " · demo data" : "";
  if (state.llmMode === "on") { b.className = "badge badge-ok"; b.textContent = "LLM connected" + suffix; }
  else if (state.llmMode === "off") { b.className = "badge badge-off"; b.textContent = "catalog mode (no LLM)" + suffix; }
  else { b.className = "badge badge-pending"; b.textContent = "checking LLM…"; }
}

async function maybeInstallMock() {
  if (!window.MOCK_FALLBACK) return;
  if (new URLSearchParams(location.search).get("mock") === "1") {
    window.fetch = window.MOCK_FALLBACK();
    state.mock = true;
    return;
  }
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 900);
    const h = await fetch("/health", { signal: ctrl.signal, cache: "no-store" });
    clearTimeout(t);
    if (!h.ok) throw new Error("no api");
  } catch {
    window.fetch = window.MOCK_FALLBACK();
    state.mock = true;
  }
}

async function boot() {
  await maybeInstallMock();
  await validateStoredSession(); // dead server state -> drop saved chat too
  restoreSaved(); // replay saved transcript + last order before first paint
  renderBadge();
  try {
    const h = await get("/health");
    state.llmMode = h.llm && h.llm !== "none" ? "on" : "off";
    renderBadge();
    if (state.llmMode === "off") {
      addErrorMsg("This server has no LLM configured — I'll search the product catalog directly. Click any suggestion below.");
    }
  } catch {
    state.llmMode = "off";
    renderBadge();
  }
  bindChips();
  await refreshCart();
  els.form.addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  els.input.addEventListener("input", () => autoGrow());
  $("#newChat").addEventListener("click", newSession);
}

function autoGrow() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 140) + "px";
}

function bindChips() {
  $$(".chip").forEach((c) => (c.onclick = () => sendMessage(c.dataset.q)));
}

function hideGreeting() {
  const g = document.getElementById("greeting");
  if (g) g.remove();
}

async function newSession() {
  clearSavedSession();
  clearChat();
  localStorage.removeItem(LS_ORDER_KEY);
  state.cart = null;
  state.checkout = null;
  state.order = null;
  state.lastOrder = null;
  // NOTE: llmMode is intentionally preserved, not reset: a new conversation
  // does not change server connectivity, and resetting to "unknown" left the
  // badge stuck on "checking…" with nothing left to update it. Re-validate
  // quietly below so a changed server env still self-corrects.
  els.messages.innerHTML = "";
  els.messages.insertAdjacentHTML("afterbegin", greetingHtml());
  bindChips();
  renderBadge();
  renderCart();
  renderCheckout();
  els.input.focus();
  try {
    const h = await get("/health");
    state.llmMode = h.llm && h.llm !== "none" ? "on" : "off";
  } catch {
    if (state.mock) state.llmMode = "off";
  }
  renderBadge();
}

function greetingHtml() {
  return `<div id="greeting" class="greeting">
    <span class="kicker">the good-stuff finder</span>
    <h2>What are we<br />shopping for <em>today?</em></h2>
    <p class="lede">Tell Shop-Pilot the thing, the budget, the vibe. It hunts the catalog, checks reviews, drops it in your trolley — and only places an order when <b>you</b> say so.</p>
    <div class="chips" id="greetChips">
      <button class="chip" data-q="I need wireless headphones under ₹10,000 with good battery life and good reviews"><span>Headphones under ₹10k</span><span class="arr">→</span></button>
      <button class="chip" data-q="Find a portable bluetooth speaker with deep bass for picnics"><span>Speaker, deep bass</span><span class="arr">→</span></button>
      <button class="chip" data-q="Show me a smartwatch with heart-rate tracking"><span>Heart-rate smartwatch</span><span class="arr">→</span></button>
      <button class="chip" data-q="Compare the best wireless headphones with the budget option"><span>Compare two headphones</span><span class="arr">→</span></button>
    </div>
    <p class="fine"><b>✳</b> try one — or just type your own wish list below</p>
  </div>`;
}

boot();
