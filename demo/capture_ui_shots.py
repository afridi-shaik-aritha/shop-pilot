"""Regenerate the README UI screenshots (assets/ui-*.png) for the current build.

Drives the self-contained preview build (?shot= autopilot) inside headless
Chrome over the DevTools protocol, waiting for each UI state's DOM marker
before capturing, so the images always show the real mid/end states.

Requirements: node >= 21 (global fetch/WebSocket) and Google Chrome.
Usage:
    python demo/capture_ui_shots.py [--out assets] [--serve-dir app/static]
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"

CHROME_CANDIDATES = [
    os.environ.get("SHOT_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

NODE_DRIVER = r"""
import fs from "fs";
const PORT = Number(process.env.CHROME_DEBUG_PORT);
const BASE = process.env.SHOT_BASE_URL;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function newTarget(url) {
  for (let i = 0; i < 30; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
      if (r.ok) return await r.json();
    } catch {}
    await wait(250);
  }
  throw new Error("chrome debug port not reachable");
}
const target = await newTarget(BASE);
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
};
const send = (method, params = {}) => new Promise((res) => {
  const i = ++id; pending.set(i, res);
  ws.send(JSON.stringify({ id: i, method, params }));
});
await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false });

async function evalv(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
  return r.result ? r.result.value : undefined;
}
async function cond(expr, timeoutMs = 40000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try { if (await evalv(expr) === true) return true; } catch {}
    await wait(150);
  }
  return false;
}
const modes = [
  { key: "greeting", url: BASE,                     sel: ".chip",              settle: 1500 },
  { key: "cart",     url: BASE + "?shot=cart",      sel: ".cart-item",         settle: 1000 },
  { key: "gate",     url: BASE + "?shot=gate",      sel: "#confirmBtn",        settle: 6000 },
  { key: "order",    url: BASE + "?shot=order",     sel: ".order-ok",          settle: 6500 },
];
for (const m of modes) {
  await send("Page.navigate", { url: m.url });
  if (!await cond('document.readyState === "complete"')) { console.log(`${m.key}: load timeout`); continue; }
  // fresh browser state per shot: previous runs persist chat/orders in localStorage
  await evalv("localStorage.clear()");
  await send("Page.navigate", { url: m.url });
  const ok = await cond(`document.readyState === "complete" && !!document.querySelector('${m.sel}')`);
  if (!ok) { console.log(`${m.key}: TIMEOUT waiting for ${m.sel}`); continue; }
  await wait(m.settle);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(`${process.env.SHOT_OUT}/ui-${m.key}.png`, Buffer.from(shot.data, "base64"));
  console.log(`${m.key}: captured after ${m.sel}`);
}
ws.close();
"""


def find_chrome() -> str:
    for cand in CHROME_CANDIDATES:
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("Chrome not found — set SHOT_CHROME to the binary path")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "assets"))
    ap.add_argument("--serve-dir", default=str(STATIC))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) build the self-contained preview WITH the ?shot= autopilot
    subprocess.run([sys.executable, str(ROOT / "demo" / "build_ui_preview.py"), "--shot"], check=True)

    # 2) serve the static dir locally (404 /health => the page auto-uses mock mode)
    server = ThreadingHTTPServer(("127.0.0.1", 0), SimpleHTTPRequestHandler)
    server_port = server.server_address[1]
    prev_cwd = os.getcwd()
    os.chdir(args.serve_dir)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # 3) headless Chrome with a remote-debugging port
    debug_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="spchrome-"))
    chrome = subprocess.Popen(
        [
            find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
            f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        env = dict(os.environ)
        env.update({
            "CHROME_DEBUG_PORT": str(debug_port),
            "SHOT_BASE_URL": f"http://127.0.0.1:{server_port}/ui-preview.html",
            "SHOT_OUT": str(out_dir),
        })
        proc = subprocess.run(
            ["node", "--input-type=module", "-"],
            input=NODE_DRIVER, text=True, capture_output=True, env=env,
        )
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            return proc.returncode
    finally:
        chrome.terminate()
        server.shutdown()
        chrome.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)
        try:
            os.chdir(prev_cwd)
        except OSError:
            pass

    for name in ("ui-greeting.png", "ui-cart.png", "ui-gate.png", "ui-order.png"):
        p = out_dir / name
        if p.exists():
            print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
