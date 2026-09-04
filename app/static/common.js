/* Shop-Pilot shared frontend module: DOM helpers, API client, product art,
   product cards, and the product details modal. Imported by app.js (chat)
   and shop.js (storefront). No top-level DOM access — safe to import anywhere.
   Cart sessions share one localStorage key so both pages see one trolley. */
"use strict";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const LS_KEY = "shopPilot.session";

export const storedSessionId = () => {
  try { return localStorage.getItem(LS_KEY) || null; } catch { return null; }
};
export const storeSessionId = (id) => {
  try { localStorage.setItem(LS_KEY, id); } catch { /* private mode */ }
};
export const clearStoredSession = () => {
  try { localStorage.removeItem(LS_KEY); } catch {}
};

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

export const inr = (n) => {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return "₹" + v.toLocaleString("en-IN", {
    minimumFractionDigits: v % 1 ? 2 : 0,
    maximumFractionDigits: 2,
  });
};

export const uid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + Math.random().toString(16).slice(2));

/* ---------- API client (timeout + {status} errors) ---------- */
export async function api(method, path, body, { timeoutMs = 25000 } = {}) {
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
export const get = (p) => api("GET", p);
export const post = (p, b) => api("POST", p, b);
export const patch = (p, b) => api("PATCH", p, b);
export const del = (p) => api("DELETE", p);

/* Ensure a server session id, minting via POST /sessions (mock-compatible). */
export async function ensureSessionId() {
  let sid = storedSessionId();
  if (sid) return sid;
  try {
    sid = (await post("/sessions", {})).session_id;
  } catch {
    sid = (await get("/cart")).session_id; // legacy bootstrap (mock)
  }
  storeSessionId(sid);
  return sid;
}

/* ---------- product sticker art (deterministic, no images needed) ---------- */
const ART_PALETTE = ["#ffd43b", "#ffb25e", "#ffa07a", "#c8e6b0", "#b3d0f2", "#e3c3ef", "#f7d9a0", "#f2bfbf"];
const ART_ICONS = {
  headphones: `<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13.5" width="4.2" height="6.5" rx="2"/><rect x="16.8" y="13.5" width="4.2" height="6.5" rx="2"/>`,
  speaker: `<rect x="7" y="4" width="10" height="16" rx="2.5"/><circle cx="12" cy="10.5" r="2.4"/><path d="M9.4 16h5.2"/>`,
  watch: `<rect x="7.5" y="4.5" width="9" height="15" rx="2.6"/><path d="M9.6 4.5V2.6h4.8v1.9M9.6 19.5v1.9h4.8v-1.9"/><path d="M10.4 12h1.5l.7-1.8 1.1 2.4"/>`,
  bag: `<path d="M6 8h12l-1.1 10.5a2 2 0 0 1-2 1.7H9.1a2 2 0 0 1-2-1.7L6 8z"/><path d="M9 10.5V7a3 3 0 0 1 6 0v3.5"/>`,
};
export function pickArt(p) {
  const cat = String(p.category || "").toLowerCase();
  if (cat.includes("headphone") || cat.includes("earphone") || cat.includes("bud")) return "headphones";
  if (cat.includes("speaker")) return "speaker";
  if (cat.includes("watch")) return "watch";
  return "bag";
}
export function artColor(id) {
  let s = 0;
  for (const ch of String(id)) s += ch.charCodeAt(0);
  return ART_PALETTE[s % ART_PALETTE.length];
}
export function artHtml(p, cls = "pc-art", size = 26) {
  const color = artColor(p.product_id);
  return `<span class="${cls}" style="background:${color}" aria-hidden="true">` +
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ART_ICONS[pickArt(p)]}</svg></span>`;
}

export function cardHtml(p) {
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

/* Product details dialog. Callers inject page-specific behavior:
   modalRoot (container), loadProduct (fetch with page's session handling),
   notify (toast), addToCart. Focus-trapped, ESC/backdrop close. */
export async function openProductModal({ productId, modalRoot, loadProduct, notify, addToCart }) {
  try {
    const p = await loadProduct(productId);
    const stock = p.stock ?? (p.availability === false ? 0 : 1);
    const inStock = p.availability !== false && stock > 0;
    const rating = Number(p.rating);
    const ratingText = Number.isFinite(rating) ? rating.toFixed(1) : "—";
    modalRoot.innerHTML = `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-label="${esc(p.name)}">
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
        const focusables = $$('button, [href], input, [tabindex]:not([tabindex="-1"])', modalRoot)
          .filter((el) => !el.disabled);
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const tabs = [$("#tabSpecs", modalRoot), $("#tabReviews", modalRoot)];
        if (tabs.includes(document.activeElement)) {
          e.preventDefault();
          (document.activeElement === tabs[0] ? tabs[1] : tabs[0]).focus();
        }
      }
    };
    const close = () => {
      window.removeEventListener("keydown", onKey);
      modalRoot.innerHTML = "";
      if (prevFocus && prevFocus.focus) prevFocus.focus();
    };
    window.addEventListener("keydown", onKey);
    $(".m-close", modalRoot).onclick = close;
    $(".modal-backdrop", modalRoot).addEventListener("click", (e) => { if (e.target.classList.contains("modal-backdrop")) close(); }, { once: true });
    $("#mAdd", modalRoot).onclick = () => { addToCart(p.product_id, 1, p.name); close(); };
    $(".m-close", modalRoot).focus();

    const content = $("#modalContent");
    const specsHtml = `<table class="specs">${Object.entries(p.specs || {})
      .map(([k, v]) => `<tr><td>${esc(String(k).replace(/_/g, " "))}</td><td>${esc(v)}</td></tr>`).join("")}</table>`;
    content.innerHTML = specsHtml || "<p class='empty'>No specifications listed.</p>";

    $("#tabSpecs", modalRoot).onclick = () => {
      $("#tabSpecs", modalRoot).classList.add("on"); $("#tabReviews", modalRoot).classList.remove("on");
      $("#tabSpecs", modalRoot).setAttribute("aria-selected", "true");
      $("#tabReviews", modalRoot).setAttribute("aria-selected", "false");
      content.innerHTML = specsHtml || "<p class='empty'>No specifications listed.</p>";
    };
    $("#tabReviews", modalRoot).onclick = async () => {
      $("#tabReviews", modalRoot).classList.add("on"); $("#tabSpecs", modalRoot).classList.remove("on");
      $("#tabReviews", modalRoot).setAttribute("aria-selected", "true");
      $("#tabSpecs", modalRoot).setAttribute("aria-selected", "false");
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
  } catch (err) { notify("Could not load product: " + err.message, "err"); }
}
