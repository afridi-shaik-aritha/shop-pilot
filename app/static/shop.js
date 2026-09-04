/* Shop-Pilot storefront: browse, search, add. Checkout lives in the chat
   app (/); the trolley is shared through the same session id. */
"use strict";

import {
  $, $$, esc, inr, get, post, del, cardHtml, openProductModal, ensureSessionId,
  storedSessionId, clearStoredSession,
} from "./common.js";

const state = {
  sessionId: storedSessionId(),
  category: "All",
  query: "",
  sort: "featured",
  mock: false,
};

const els = {
  grid: $("#shopGrid"),
  meta: $("#shopMeta"),
  search: $("#shopSearch"),
  sort: $("#sortSel"),
  catList: $("#catList"),
  count: $("#shopCount"),
  modalRoot: $("#modalRoot"),
  toast: $("#toast"),
  miniCart: $("#miniCart"),
  miniEmpty: $("#miniEmpty"),
  miniLines: $("#miniLines"),
  miniTotal: $("#miniTotal"),
  miniActions: $("#miniActions"),
  miniClear: $("#miniClear"),
};

function toast(msg, kind = "") {
  els.toast.hidden = false;
  els.toast.className = "toast " + kind;
  els.toast.innerHTML = `<span>${esc(msg)}</span>`;
  setTimeout(() => { els.toast.hidden = true; }, 3200);
}

async function apiWithRecovery(fn) {
  try {
    return await fn();
  } catch (err) {
    if (err && err.status === 404 && state.sessionId) {
      clearStoredSession();
      state.sessionId = null;
      await ensureSession();
      return await fn();
    }
    throw err;
  }
}

async function ensureSession() {
  if (state.sessionId) return state.sessionId;
  state.sessionId = await ensureSessionId();
  return state.sessionId;
}

function sortItems(items) {
  const arr = [...items];
  if (state.sort === "price-asc") arr.sort((a, b) => a.price - b.price);
  else if (state.sort === "price-desc") arr.sort((a, b) => b.price - a.price);
  else if (state.sort === "rating-desc") arr.sort((a, b) => b.rating - a.rating);
  return arr;
}

async function loadGrid() {
  els.meta.textContent = "Stocking the shelves…";
  try {
    let items;
    if (!state.query && state.category === "All") {
      items = (await get("/products")).products || [];
    } else {
      const body = { query: state.query || state.category, top_k: 24, filters: {} };
      if (state.category !== "All") body.filters = { category: state.category };
      items = (await post("/search", body)).products || [];
    }
    items = sortItems(items);
    els.meta.textContent = items.length
      ? `${items.length} item${items.length === 1 ? "" : "s"}${state.category !== "All" ? ` · ${state.category}` : ""}`
      : "Nothing on this shelf — try another search.";
    els.grid.innerHTML = items.map(cardHtml).join("");
    $$(".pc-add", els.grid).forEach((b) => (b.onclick = () => addToCart(b.dataset.id, 1, b.dataset.name)));
    $$(".pc-detail", els.grid).forEach((b) => (b.onclick = () => productModal(b.dataset.id)));
  } catch (err) {
    els.meta.textContent = "Shelves unavailable: " + err.message;
  }
}

async function loadCategories() {
  try {
    const data = await get("/categories");
    const cats = [{ category: "All", total: 0, in_stock: 0 }, ...(data.categories || [])];
    els.catList.innerHTML = "";
    for (const c of cats) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn-sm btn-block catbtn" + (c.category === state.category ? " on" : "");
      b.textContent = c.category === "All" ? "Everything" : `${c.category} · ${c.in_stock}`;
      b.setAttribute("aria-label", c.category === "All" ? "Show everything" : `Browse ${c.category}`);
      b.onclick = () => {
        state.category = c.category;
        $$(".catbtn", els.catList).forEach((x) => x.classList.remove("on"));
        b.classList.add("on");
        loadGrid();
      };
      els.catList.appendChild(b);
    }
  } catch {
    els.catList.innerHTML = "<p class='empty'>Shelves unavailable.</p>";
  }
}

async function refreshCount() {
  try {
    await ensureSession();
    const cart = await apiWithRecovery(() =>
      get(`/cart?session_id=${encodeURIComponent(state.sessionId)}`));
    const n = (cart.items || []).reduce((t, i) => t + i.quantity, 0);
    els.count.hidden = n === 0;
    els.count.textContent = n;
    renderMini(cart);
  } catch { /* count stays as-is when offline */ }
}

function renderMini(cart) {
  const items = (cart && cart.items) || [];
  const totals = (cart && cart.totals) || null;
  els.miniEmpty.hidden = items.length > 0;
  els.miniLines.hidden = items.length === 0;
  els.miniTotal.hidden = items.length === 0;
  els.miniActions.hidden = items.length === 0;
  els.miniLines.innerHTML = items.map((i) =>
    `<div class="mini-line"><span>${esc(i.name || i.product_id)} ×${i.quantity}</span><span>${inr((i.unit_price || 0) * i.quantity)}</span></div>`
  ).join("");
  els.miniTotal.innerHTML =
    `<div class="mini-line mini-grand"><strong>Total</strong><strong>${inr(totals?.total)}</strong></div>`;
}

/* Mini-cart Clear: two taps (button turns into 'Really clear?') so a stray
   click can't empty a shared trolley, then a live DELETE /cart. */
let miniArmed = false;
let miniArmTimer = null;
function resetMiniArm() {
  miniArmed = false;
  if (miniArmTimer) { clearTimeout(miniArmTimer); miniArmTimer = null; }
  if (els.miniClear) {
    els.miniClear.textContent = "Clear trolley";
    els.miniClear.classList.remove("btn-ink");
    els.miniClear.setAttribute("aria-label", "Empty the whole trolley");
  }
}
async function clearMiniCart() {
  try {
    await ensureSession();
    await apiWithRecovery(() =>
      del(`/cart?session_id=${encodeURIComponent(state.sessionId)}`));
    renderMini({ items: [], totals: { subtotal: 0, shipping: 0, tax: 0, total: 0 } });
    await refreshCount();
    toast("Trolley emptied — start fresh or ask for something new.");
  } catch (err) { toast("Could not clear trolley: " + err.message, "err"); }
}
function onMiniClearClick() {
  if (!miniArmed) {
    miniArmed = true;
    els.miniClear.textContent = "Really clear?";
    els.miniClear.classList.add("btn-ink");
    els.miniClear.setAttribute("aria-label", "Confirm emptying the whole trolley");
    miniArmTimer = setTimeout(resetMiniArm, 4000);
    return;
  }
  resetMiniArm();
  clearMiniCart();
}

async function loadMiniWhenOpen() {
  if (!els.miniCart || !els.miniCart.open) return;
  try {
    await ensureSession();
    const cart = await apiWithRecovery(() =>
      get(`/cart?session_id=${encodeURIComponent(state.sessionId)}`));
    renderMini(cart);
  } catch { renderMini({ items: [], totals: null }); }
}

async function addToCart(productId, quantity = 1, productName = null) {
  try {
    await ensureSession();
    // NOTE: session id is read inside the callback so a 404-recovery
    // re-mint is picked up on retry (a captured sid would replay stale).
    await apiWithRecovery(() =>
      post("/cart/items", { session_id: state.sessionId, product_id: productId, quantity }));
    await refreshCount();
    toast(`${productName || productId} added — see it in your trolley`);
  } catch (err) { toast("Could not add: " + err.message, "err"); }
}

function productModal(productId) {
  return openProductModal({
    productId,
    modalRoot: els.modalRoot,
    loadProduct: (pid) => apiWithRecovery(() => get(`/products/${pid}`)),
    notify: (msg, kind) => toast(msg, kind),
    addToCart: (pid, qty, name) => addToCart(pid, qty, name),
  });
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
  let debounce = null;
  els.search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.query = els.search.value.trim();
      loadGrid();
    }, 280);
  });
  els.sort.addEventListener("change", () => {
    state.sort = els.sort.value;
    loadGrid();
  });
  if (els.miniCart) {
    els.miniCart.addEventListener("toggle", loadMiniWhenOpen);
    els.miniClear?.addEventListener("click", onMiniClearClick);
  }
  await loadCategories();
  await loadGrid();
  await refreshCount();
}

boot();
