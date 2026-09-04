/* Shop-Pilot offline demo API.
 * Installs a deterministic mock behind the exact fetch contract the real
 * backend serves, so the whole UI flow is walkable without a server
 * (file:// previews, ?mock=1). Activated by the app when /health is
 * unreachable — see app.js boot().
 */
(function () {
  const PRODUCTS = [
    { product_id: "P01", name: "SonicWave X5 Wireless Headphones", brand: "SonicWave", category: "wireless headphones",
      description: "Wireless over-ear headphones with long 60-hour battery life and comfortable fit.",
      specs: { battery_hours: 60, bluetooth: "5.3", weight_g: 254 }, price: 8499, rating: 4.4, review_count: 2314,
      availability: true, stock: 42 },
    { product_id: "P02", name: "BassBoom Pro Wireless Headphones", brand: "BassBoom", category: "wireless headphones",
      description: "Bass-heavy wireless headphones with active noise cancellation and 40-hour battery.",
      specs: { battery_hours: 40, bluetooth: "5.2", weight_g: 281 }, price: 12999, rating: 4.6, review_count: 1871,
      availability: true, stock: 17 },
    { product_id: "P03", name: "ClearTone Wired Earphones", brand: "ClearTone", category: "wired earphones",
      description: "Budget wired in-ear earphones with microphone for calls.",
      specs: { weight_g: 18 }, price: 999, rating: 4.1, review_count: 5420,
      availability: true, stock: 200 },
    { product_id: "P04", name: "ThunderBox Bluetooth Speaker", brand: "ThunderBox", category: "bluetooth speaker",
      description: "Portable bluetooth speaker with deep bass, 24-hour playtime and splash resistance.",
      specs: { battery_hours: 24, weight_g: 680 }, price: 5999, rating: 4.5, review_count: 3102,
      availability: true, stock: 63 },
    { product_id: "P05", name: "PulseFit S2 Smartwatch", brand: "PulseFit", category: "smartwatch",
      description: "Smartwatch with heart rate tracking, SpO2 sensor and 10-day battery.",
      specs: { battery_days: 10, weight_g: 36 }, price: 7999, rating: 4.3, review_count: 1290,
      availability: true, stock: 88 },
    { product_id: "P06", name: "SonicWave X5 Refurbished Unit", brand: "SonicWave", category: "wireless headphones",
      description: "Refurbished wireless headphones, same 60-hour battery, limited warranty.",
      specs: { battery_hours: 60, weight_g: 254 }, price: 6499, rating: 4.0, review_count: 412,
      availability: false, stock: 0 },
  ];
  const REVIEWS = {
    P01: [
      { review_id: "R01", product_id: "P01", rating: 5, title: "Incredible battery", body: "Charged once on Monday, still going Friday. The 60-hour claim is real.", helpful_votes: 128 },
      { review_id: "R02", product_id: "P01", rating: 4, title: "Comfortable for long calls", body: "Ear cushions are soft. Sound is clear, bass is modest but tight.", helpful_votes: 64 },
    ],
    P02: [{ review_id: "R03", product_id: "P02", rating: 5, title: "Noise cancelling is great", body: "Blocks out the office completely. Heavy bass if that's your taste.", helpful_votes: 91 }],
    P04: [{ review_id: "R04", product_id: "P04", rating: 4, title: "Perfect picnic speaker", body: "Loud, deep bass, survived a splash at the lake.", helpful_votes: 47 }],
    P05: [
      { review_id: "R05", product_id: "P05", rating: 5, title: "Heart-rate tracking is spot on", body: "Compared against my chest strap on runs — within 2 bpm. The 10-day battery claim holds.", helpful_votes: 84 },
      { review_id: "R06", product_id: "P05", rating: 4, title: "Great value tracker", body: "SpO2 and sleep tracking work well. Wish the screen were brighter outdoors.", helpful_votes: 41 },
    ],
  };

  let session = { id: "S-demo0001", items: [] }; // {product_id, quantity}
  let checkout = null; // {checkout_id, cart_snapshot:{items,currency}, status, confirmation_token, total}
  let orders = {}; // idempotency_key -> order

  const byId = (pid) => PRODUCTS.find((p) => p.product_id === pid);
  const totalsFor = (items) => {
    let subtotal = 0;
    for (const it of items) subtotal += it.quantity * it.unit_price;
    subtotal = Math.round(subtotal * 100) / 100;
    const shipping = subtotal === 0 || subtotal >= 5000 ? 0 : 49;
    const tax = Math.round((subtotal + shipping) * 0.18 * 100) / 100;
    const total = Math.round((subtotal + shipping + tax) * 100) / 100;
    return { subtotal, shipping, tax, total };
  };

  function cartPayload() {
    const items = session.items.map((it) => {
      const p = byId(it.product_id);
      return { product_id: it.product_id, name: p ? p.name : it.product_id, quantity: it.quantity, unit_price: p ? p.price : 0 };
    });
    return { items, currency: "INR", totals: totalsFor(items) };
  }

  function http(status, body, statusText) {
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: statusText || "",
      async json() { return body; },
    };
  }
  const bad = (msg) => http(400, { detail: msg }, "Bad Request");
  const notFound = (msg) => http(404, { detail: msg }, "Not Found");

  function tokens(query) {
    return String(query || "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  }
  function searchProducts(query) {
    const t = tokens(query);
    const scored = PRODUCTS.filter((p) => p.availability).map((p) => {
      const hay = (p.name + " " + p.category + " " + p.description + " " + Object.values(p.specs).join(" ")).toLowerCase();
      const score = t.reduce((n, tok) => n + (hay.includes(tok) ? 1 : 0), 0);
      return { p, score };
    });
    scored.sort((a, b) => b.score - a.score || a.p.price - b.p.price);
    return scored.filter((s) => s.score > 0).map((s) => s.p).concat(scored.filter((s) => s.score === 0).map((s) => s.p));
  }

  async function chatReply(message) {
    const q = String(message || "").toLowerCase();
    const tools = ["search_products", "get_product"];
    let text;
    let products = [];
    if (q.includes("compare")) {
      tools.push("compare_products");
      products = ["P01", "P02", "P03"].map(byId);
      text = "Here's the side-by-side:\n\n**SonicWave X5 (P01)** · ₹8,499 · ★4.4 · 60-hr battery · in stock\n**BassBoom Pro (P02)** · ₹12,999 · ★4.6 · ANC · in stock\n**ClearTone (P03)** · ₹999 · ★4.1 · wired · in stock\n\nFor ₹10k budgets the **X5** is the sweet spot — under budget, longer battery, great reviews. Use the cards below to add one to your cart.";
    } else {
      let pick = null;
      if (q.includes("headphone")) pick = "P01";
      else if (q.includes("speaker")) pick = "P04";
      else if (q.includes("smartwatch") || q.includes("watch")) pick = "P05";
      const p = pick ? byId(pick) : searchProducts(message)[0];
      if (p) {
        tools.push("add_to_cart");
        products = [p];
        const row = session.items.find((i) => i.product_id === p.product_id);
        if (row) row.quantity += 1;
        else session.items.push({ product_id: p.product_id, quantity: 1 });
        text = `**${p.name} (${p.product_id})** is your best match — **₹${p.price.toLocaleString("en-IN")}** · ★${p.rating} (${p.review_count.toLocaleString("en-IN")} reviews) · ${p.description.split(".")[0]}. Added 1× to your cart — totals are in the right panel, or use the card below. Tap **Prepare checkout** to review an itemized summary and confirm explicitly.`;
      } else {
        text = "I couldn't find a strong match. Try 'headphones under 10000', 'bluetooth speaker', or 'smartwatch'.";
      }
    }
    return { reply: text, tools, products };
  }

  function checkoutPayload() {
    const items = session.items.map((it) => {
      const p = byId(it.product_id);
      return { product_id: it.product_id, name: p.name, quantity: it.quantity, unit_price: p.price };
    });
    const totals = totalsFor(items);
    return {
      checkout_id: "C-demo" + Math.random().toString(16).slice(2, 8),
      cart_snapshot: { items, currency: "INR" },
      status: "AWAITING_CONFIRMATION",
      confirmation_token: "demo" + Math.random().toString(16).slice(2, 14),
      total: totals.total,
    };
  }

  function createMockFetch() {
    const delay = (ms) => new Promise((r) => setTimeout(r, ms));
    return async function mockFetch(input, opts = {}) {
      await delay(180); // feels like a real round trip
      const url = String(input);
      const [path, query] = url.split("?");
      const params = new URLSearchParams(query || "");
      const method = (opts.method || "GET").toUpperCase();
      let body = {};
      if (opts.body) { try { body = JSON.parse(opts.body); } catch { /* ignore */ } }

      if (path === "/health") return http(200, { ok: true, llm: "openrouter" });

      if (path === "/sessions" && method === "POST") {
        return http(200, { session_id: session.id });
      }

      const sid = body.session_id || params.get("session_id");
      void sid;
      if (path === "/cart" && method === "GET") {
        const qsid = params.get("session_id");
        if (!qsid) {
          // Mirror the real API: anonymous reads require a session id.
          // The mock keeps one demo session, so mint it explicitly.
          return http(200, { session_id: session.id, ...cartPayload() });
        }
        return http(200, { session_id: session.id, ...cartPayload() });
      }

      const mItem = path.match(/^\/cart\/items\/([\w\-.]+)$/);
      if (mItem) {
        const pid = decodeURIComponent(mItem[1]);
        if (method === "PATCH") {
          const row = session.items.find((i) => i.product_id === pid);
          if (!row) return bad("not in cart: " + pid);
          if (body.quantity <= 0) session.items = session.items.filter((i) => i.product_id !== pid);
          else row.quantity = body.quantity;
          return http(200, { session_id: session.id, ...cartPayload() });
        }
        if (method === "DELETE") {
          session.items = session.items.filter((i) => i.product_id !== pid);
          return http(200, { session_id: session.id, ...cartPayload() });
        }
      }
      if (path === "/cart/items" && method === "POST") {
        const p = byId(body.product_id);
        if (!p) return bad("unknown product: " + body.product_id);
        const qty = Math.max(1, Math.min(99, body.quantity || 1));
        const row = session.items.find((i) => i.product_id === body.product_id);
        if (row) row.quantity += qty;
        else session.items.push({ product_id: body.product_id, quantity: qty });
        return http(200, { session_id: session.id, ...cartPayload() });
      }

      if (path === "/checkout/prepare" && method === "POST") {
        if (!session.items.length) return bad("cart is empty");
        checkout = checkoutPayload();
        return http(200, checkout);
      }
      if (path === "/checkout/confirm" && method === "POST") {
        if (!checkout) return bad("no checkout prepared");
        if (body.confirmation_token !== checkout.confirmation_token) return bad("confirmation token does not match this checkout");
        checkout.status = "CONFIRMED";
        return http(200, checkout);
      }
      if (path === "/checkout/cancel" && method === "POST") {
        if (!checkout) return bad("no checkout prepared");
        checkout.status = "REJECTED";
        return http(200, checkout);
      }
      if (path === "/checkout" && method === "GET") {
        if (!checkout) return bad("no checkout prepared");
        return http(200, checkout);
      }

      if (path === "/orders" && method === "POST") {
        const key = body.idempotency_key || "";
        if (orders[key]) return http(200, orders[key]);
        if (!checkout || checkout.status !== "CONFIRMED") return bad("order requires explicit confirmation first");
        checkout.status = "COMPLETED"; // backend flips the checkout state too
        const order = {
          order_id: "O-demo" + Math.random().toString(16).slice(2, 8),
          checkout_id: checkout.checkout_id,
          items: checkout.cart_snapshot.items,
          total: checkout.total,
          status: "COMPLETED",
          idempotency_key: key,
        };
        orders[key] = order;
        for (const it of checkout.cart_snapshot.items) {
          const p = byId(it.product_id);
          if (p) {
            p.stock = Math.max(0, (p.stock || 0) - it.quantity);
            if (p.stock === 0) p.availability = false;
          }
        }
        session.items = []; // purchased lines leave the trolley
        return http(200, order);
      }

      const mProd = path.match(/^\/products\/([\w\-.]+)$/);
      if (mProd) {
        const p = byId(decodeURIComponent(mProd[1]));
        if (!p) return notFound("unknown product: " + mProd[1]);
        return http(200, p);
      }
      const mRev = path.match(/^\/products\/([\w\-.]+)\/reviews$/);
      if (mRev) return http(200, { reviews: REVIEWS[decodeURIComponent(mRev[1])] || [] });

      if (path === "/search" && method === "POST") {
        const top = searchProducts(body.query).slice(0, Math.max(1, Math.min(50, body.top_k || 5)));
        if (!top.length || !String(body.query || "").trim()) {
          return http(200, { products: [] });
        }
        return http(200, {
          products: top.map((p) => ({
            product_id: p.product_id, name: p.name, price: p.price, rating: p.rating, score: 0.5,
            category: p.category, brand: p.brand,
            availability: p.availability, stock: p.stock, review_count: p.review_count,
          })),
        });
      }

      if (path === "/chat" && method === "POST") {
        const out = await chatReply(body.message);
        return http(200, { session_id: session.id, reply: out.reply, status: "ok", steps: 3, tool_calls: out.tools.length, tools: out.tools, products: out.products || [] });
      }

      return notFound(path);
    };
  }

  window.MOCK_FALLBACK = createMockFetch;
})();
