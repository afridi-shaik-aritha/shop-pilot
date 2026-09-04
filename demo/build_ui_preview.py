"""Build app/static/ui-preview.html — a self-contained single-file copy of the
web UI (CSS, mock API, and app JS inlined) for offline previews and screenshots.

Usage:
    python demo/build_ui_preview.py          # default build (no autopilot)
    python demo/build_ui_preview.py --shot   # also inject the ?shot= screenshot autopilot
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
OUT = STATIC / "ui-preview.html"

# Injected only for --shot builds. Drives a canned mock conversation when the
# page is opened with ?shot=cart|gate|order so headless Chrome can capture the
# mid/end UI states. Never present in default builds.
# NOTE: settling is handled by explicit DOM-marker waits in capture_ui_shots.py
# (waitFor #prepareBtn/#confirmBtn); no arbitrary sleep is needed here.
SHOT_AUTOPILOT = """<script>
/* Shot autopilot (--shot build only). Active only when opened with ?shot=. */
(function () {
  var shot = new URLSearchParams(location.search).get("shot");
  if (!shot || !window.MOCK_FALLBACK) return;
  function waitFor(sel, cb, n) {
    n = n || 0;
    var el = document.querySelector(sel);
    if (el) return cb(el);
    if (n > 600) return;
    setTimeout(function () { waitFor(sel, cb, n + 1); }, 60);
  }
  /* The suggestion chip exists in static HTML before boot() wires its handler,
     so keep poking until the greeting is gone (a real send has started). */
  var pokes = 0;
  function pokeChip() {
    if (document.getElementById("greeting")) {
      var chip = document.querySelector(".chip");
      if (chip) { try { chip.click(); } catch (e) {} }
      if (++pokes < 200) { setTimeout(pokeChip, 100); return; }
    }
    waitFor("#prepareBtn", function (prepare) {
      if (shot === "cart") return settle();
      prepare.click();
      waitFor("#confirmBtn", function (confirm) {
        if (shot === "gate") return settle();
        confirm.click();
        settle();
      });
    });
  }
  pokeChip();
  function settle() { /* DOM-marker waits in the driver handle settling */ }
})();
</script>
"""


def main() -> int:
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    mock = (STATIC / "mock.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    # drop external asset tags; we inline everything below
    html = html.replace('  <link rel="stylesheet" href="/static/styles.css" />', "")
    html = html.replace('  <script src="/static/mock.js"></script>\n', "")
    html = html.replace('  <script type="module" src="/static/app.js"></script>\n', "")

    combined = (
        html.replace("</head>", f"<style>\n{css}\n</style></head>", 1)
        .replace("</body>", f"<script>\n{mock}\n</script>\n<script>\n{app}\n</script>\n</body>", 1)
    )
    if "--shot" in sys.argv[1:]:
        combined = combined.replace("</body>", SHOT_AUTOPILOT + "</body>", 1)
    OUT.write_text(combined, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
