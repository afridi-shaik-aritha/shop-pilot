"""Deterministic catalog expansion: P01-P06 (+ R01-R06) are preserved
byte-identically; P07-P50 (+ reviews) are generated from the tables below.

Usage:  python demo/seed_catalog.py [--write]
Without --write it only reports what would change. With --write it rewrites
data/products.json, data/reviews.json (sorted-keys, single-line, matching the
existing style) and regenerates the PRODUCTS/REVIEWS constants in
app/static/mock.js from the same seed so mock and server never drift.

Copy rules (protect pinned benchmarks): new headphone blurbs never use
"long"/"life" (keeps P01 rank-1 on the demo query); new speaker blurbs never
use "picnic(s)" (keeps P04 rank-1 on its dataset query).
"""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RNG = random.Random(20260904)

# (id, name, brand, category, price, rating, review_count, stock, blurb, specs)
NEW_PRODUCTS = [
    # wireless headphones
    ("P07", "AudioNest Hush One Wireless Headphones", "AudioNest", "wireless headphones", 9999, 4.3, 864, 25,
     "Closed-back wireless headphones with hybrid noise cancellation and 45-hour playback on a single charge.",
     {"battery_hours": 45, "bluetooth": "5.3", "weight_g": 262}),
    ("P08", "BeatCraft Studio Max Wireless Headphones", "BeatCraft", "wireless headphones", 14999, 4.7, 1204, 12,
     "Flagship wireless headphones with studio-tuned drivers and plush memory-foam cushions.",
     {"battery_hours": 38, "bluetooth": "5.4", "weight_g": 295}),
    ("P09", "EchoPods Lite Wireless Headphones", "EchoPods", "wireless headphones", 4999, 4.0, 2310, 60,
     "Lightweight wireless headphones with punchy sound and fast charging — 10 minutes gives 5 hours.",
     {"battery_hours": 35, "bluetooth": "5.2", "weight_g": 210}),
    ("P10", "SoundLoom Travel Wireless Headphones", "SoundLoom", "wireless headphones", 7999, 4.2, 540, 0,
     "Foldable wireless headphones with multipoint pairing for laptop and phone.",
     {"battery_hours": 40, "bluetooth": "5.3", "weight_g": 240}),
    # bluetooth speakers
    ("P11", "RumbleBox Party Bluetooth Speaker", "RumbleBox", "bluetooth speaker", 8999, 4.4, 976, 34,
     "Room-filling bluetooth speaker with thumping bass and LED light ring for house parties.",
     {"battery_hours": 18, "weight_g": 1200}),
    ("P12", "SoundCrest Mini Bluetooth Speaker", "SoundCrest", "bluetooth speaker", 2999, 4.2, 3420, 120,
     "Pocket-size bluetooth speaker with clear mids and 12-hour playback for daily use.",
     {"battery_hours": 12, "weight_g": 340}),
    ("P13", "BassNest Outdoor Bluetooth Speaker", "BassNest", "bluetooth speaker", 7499, 4.5, 689, 28,
     "Rugged bluetooth speaker with deep bass radiator and IPX7 waterproofing for poolside days.",
     {"battery_hours": 20, "weight_g": 820}),
    # smartwatches
    ("P14", "WristFit GTR Smartwatch", "WristFit", "smartwatch", 10999, 4.5, 743, 41,
     "AMOLED smartwatch with dual-band GPS, heart rate variability and 14-day battery.",
     {"battery_days": 14, "weight_g": 42}),
    ("P15", "BeatBand Active Smartwatch", "BeatBand", "smartwatch", 4999, 4.1, 1876, 95,
     "Slim smartwatch with all-day heart rate monitoring, step counting and 7-day battery.",
     {"battery_days": 7, "weight_g": 29}),
    ("P16", "OrbitWatch Classic Smartwatch", "OrbitWatch", "smartwatch", 14999, 4.6, 312, 0,
     "Steel smartwatch with ECG, blood oxygen and wireless charging.",
     {"battery_days": 5, "weight_g": 58}),
    # wired earphones
    ("P17", "WireTune Pro Wired Earphones", "WireTune", "wired earphones", 1499, 4.3, 2874, 150,
     "Hi-res certified wired earphones with braided cable and in-line controls.",
     {"weight_g": 22}),
    ("P18", "AudioPlug Bass Wired Earphones", "AudioPlug", "wired earphones", 699, 3.9, 4102, 300,
     "Extra-bass wired earphones with snug fit for workouts.",
     {"weight_g": 16}),
    # laptops
    ("P19", "VoltBook Air 14 Laptop", "VoltBook", "laptop", 54990, 4.5, 689, 22,
     "Thin 14-inch laptop with 16GB RAM, 512GB SSD and 18-hour battery for workdays.",
     {"ram_gb": 16, "storage_gb": 512, "weight_g": 1290}),
    ("P20", "VoltBook Pro 16 Laptop", "VoltBook", "laptop", 89990, 4.7, 412, 9,
     "Creator laptop with dedicated graphics, 32GB RAM and color-accurate display.",
     {"ram_gb": 32, "storage_gb": 1024, "weight_g": 2100}),
    ("P21", "CompuPro Everyday 15 Laptop", "CompuPro", "laptop", 42990, 4.2, 1530, 47,
     "Everyday 15-inch laptop with backlit keyboard and fast charging.",
     {"ram_gb": 8, "storage_gb": 512, "weight_g": 1750}),
    ("P22", "CompuPro Budget 14 Laptop", "CompuPro", "laptop", 29990, 3.9, 2210, 83,
     "Affordable 14-inch laptop for students with all-day battery.",
     {"ram_gb": 8, "storage_gb": 256, "weight_g": 1490}),
    # smartphones
    ("P23", "NovaMobile X5 Smartphone", "NovaMobile", "smartphone", 32999, 4.4, 1980, 56,
     "5G smartphone with 120Hz AMOLED display and 50MP camera.",
     {"storage_gb": 128, "battery_mah": 5000}),
    ("P24", "NovaMobile Ultra Smartphone", "NovaMobile", "smartphone", 59999, 4.6, 870, 23,
     "Flagship smartphone with periscope zoom camera and titanium frame.",
     {"storage_gb": 256, "battery_mah": 5400}),
    ("P25", "OrbitPhone Lite Smartphone", "OrbitPhone", "smartphone", 15999, 4.1, 3120, 110,
     "Budget 5G smartphone with big battery and clean software.",
     {"storage_gb": 128, "battery_mah": 6000}),
    ("P26", "OrbitPhone Mini Smartphone", "OrbitPhone", "smartphone", 24999, 4.3, 640, 38,
     "Compact smartphone with one-hand friendly size and wireless charging.",
     {"storage_gb": 128, "battery_mah": 4200}),
    # tablets
    ("P27", "SlatePro 11 Tablet", "SlatePro", "tablet", 38990, 4.5, 520, 31,
     "11-inch tablet with stylus support and 12-hour battery for notes and art.",
     {"storage_gb": 128, "weight_g": 480}),
    ("P28", "TabNest Kids Tablet", "TabNest", "tablet", 12999, 4.2, 1430, 74,
     "Kid-proof tablet with parental controls and bumper case.",
     {"storage_gb": 64, "weight_g": 550}),
    ("P29", "SlatePro Max 13 Tablet", "SlatePro", "tablet", 64990, 4.6, 210, 14,
     "Large 13-inch tablet with desktop-class chip for video editing.",
     {"storage_gb": 256, "weight_g": 680}),
    # mechanical keyboards
    ("P30", "KeyForge TKL Mechanical Keyboard", "KeyForge", "mechanical keyboard", 7999, 4.6, 930, 52,
     "Hot-swappable mechanical keyboard with tactile switches and PBT keycaps.",
     {"keys": 87}),
    ("P31", "ClickClack 60 Mechanical Keyboard", "ClickClack", "mechanical keyboard", 5999, 4.4, 1260, 68,
     "Compact 60 percent mechanical keyboard with linear switches and RGB.",
     {"keys": 61}),
    ("P32", "KeyForge Wireless Mechanical Keyboard", "KeyForge", "mechanical keyboard", 9999, 4.5, 410, 0,
     "Wireless mechanical keyboard with 2.4GHz and triple Bluetooth pairing.",
     {"keys": 98, "battery_hours": 200}),
    # wireless mice
    ("P33", "GlidePro Silent Wireless Mouse", "GlidePro", "wireless mouse", 1999, 4.3, 2870, 140,
     "Silent-click wireless mouse with ergonomic shape for office work.",
     {"dpi": 3200}),
    ("P34", "SwiftClick Gaming Wireless Mouse", "SwiftClick", "wireless mouse", 4999, 4.6, 1150, 47,
     "Esports-grade wireless mouse with 26000 DPI sensor and 90-hour battery.",
     {"dpi": 26000, "battery_hours": 90}),
    ("P35", "GlidePro Travel Wireless Mouse", "GlidePro", "wireless mouse", 1499, 4.1, 1980, 190,
     "Slim wireless mouse that slips into a laptop sleeve.",
     {"dpi": 1600}),
    # monitors
    ("P36", "ViewMax 27 4K Monitor", "ViewMax", "monitor", 32999, 4.5, 480, 26,
     "27-inch 4K monitor with HDR and height-adjustable stand.",
     {"size_in": 27}),
    ("P37", "ClearPanel 24 Office Monitor", "ClearPanel", "monitor", 13999, 4.3, 1120, 58,
     "Eye-care 24-inch monitor with low blue light for long workdays.",
     {"size_in": 24}),
    ("P38", "ViewMax 34 Ultrawide Monitor", "ViewMax", "monitor", 54999, 4.7, 230, 11,
     "Curved 34-inch ultrawide monitor with 144Hz refresh for gaming.",
     {"size_in": 34}),
    # cameras
    ("P39", "LensCraft M50 Mirrorless Camera", "LensCraft", "mirrorless camera", 64990, 4.6, 340, 16,
     "24MP mirrorless camera with 4K video and in-body stabilization.",
     {"megapixels": 24}),
    ("P40", "FotoPro Instant Camera", "FotoPro", "instant camera", 8999, 4.2, 1740, 92,
     "Point-and-shoot instant camera with auto exposure for parties.",
     {"megapixels": 12}),
    ("P41", "LensCraft Pro Mirrorless Camera", "LensCraft", "mirrorless camera", 129990, 4.8, 120, 6,
     "Full-frame mirrorless camera with dual card slots for professionals.",
     {"megapixels": 33}),
    # backpacks
    ("P42", "TrailPack 45 Hiking Backpack", "TrailPack", "backpack", 4999, 4.5, 860, 73,
     "45-litre hiking backpack with rain cover and ventilated back.",
     {"capacity_l": 45}),
    ("P43", "UrbanHaul Laptop Backpack", "UrbanHaul", "backpack", 2999, 4.4, 2130, 0,
     "Water-repellent laptop backpack with USB passthrough and 15-inch sleeve.",
     {"capacity_l": 25}),
    ("P44", "TrailPack Daypack 20 Backpack", "TrailPack", "backpack", 1999, 4.3, 1470, 120,
     "Light 20-litre daypack backpack for commutes and short trails.",
     {"capacity_l": 20}),
    # running shoes
    ("P45", "StrideX Marathon Running Shoes", "StrideX", "running shoes", 8999, 4.6, 790, 44,
     "Carbon-plated running shoes with responsive foam for race day.",
     {"weight_g": 220}),
    ("P46", "RunFlex Daily Running Shoes", "RunFlex", "running shoes", 5999, 4.4, 1680, 87,
     "Cushioned daily running shoes with breathable knit upper.",
     {"weight_g": 280}),
    ("P47", "StrideX Trail Running Shoes", "StrideX", "running shoes", 7499, 4.5, 530, 39,
     "Grippy trail running shoes with rock plate for uneven paths.",
     {"weight_g": 310}),
    # coffee makers
    ("P48", "BrewMate Drip Coffee Maker", "BrewMate", "coffee maker", 4999, 4.3, 920, 51,
     "12-cup drip coffee maker with programmable timer and thermal carafe.",
     {"capacity_cups": 12}),
    ("P49", "CafePress Espresso Coffee Maker", "CafePress", "coffee maker", 18999, 4.6, 380, 19,
     "Espresso coffee maker with steam wand for lattes at home.",
     {"pressure_bar": 15}),
    ("P50", "BrewMate French Press Coffee Maker", "BrewMate", "coffee maker", 1499, 4.4, 2310, 160,
     "Classic French press coffee maker with stainless filter.",
     {"capacity_cups": 8}),
]

REVIEW_TITLES = [
    "Does the job well", "Great for the price", "Exceeded expectations",
    "Solid pick", "Very happy", "Good, minor quibbles",
]
REVIEW_BODIES = [
    "Build quality feels premium for this price. Setup took minutes and daily use has been flawless.",
    "Does exactly what it promises. Delivery was quick and packaging was neat.",
    "A noticeable upgrade over my old one. The attention to detail really shows.",
    "Works great so far. A couple of small quirks but nothing that bothers me day to day.",
    "Bought a second one as a gift after using mine for a month. Highly recommended.",
    "Performance matches the description. Would buy again without hesitation.",
]


def build_products(existing):
    out = list(existing)
    for pid, name, brand, category, price, rating, rc, stock, blurb, specs in NEW_PRODUCTS:
        out.append({
            "availability": stock > 0,
            "brand": brand,
            "category": category,
            "description": blurb,
            "name": name,
            "price": float(price),
            "product_id": pid,
            "rating": float(rating),
            "review_count": rc,
            "specs": specs,
            "stock": stock,
        })
    return out


def build_reviews(existing):
    out = list(existing)
    rid = 7
    for pid, name, brand, category, price, rating, rc, stock, blurb, specs in NEW_PRODUCTS:
        feature = blurb.split(".")[0].split(" with ")[0]
        for i in range(3):
            r = max(1, min(5, round(rating) + RNG.choice([0, 0, 0, 1, -1])))
            out.append({
                "body": f"{REVIEW_BODIES[(rid + i) % len(REVIEW_BODIES)]} {feature}.",
                "helpful_votes": RNG.randint(5, 200),
                "product_id": pid,
                "rating": r,
                "review_id": f"R{rid:02d}",
                "title": REVIEW_TITLES[(rid + i) % len(REVIEW_TITLES)],
            })
            rid += 1
    return out


def dump_pretty(items):
    return json.dumps(items, sort_keys=True, indent=2) + "\n"


def regen_mock(products, reviews):
    mock_path = ROOT / "app" / "static" / "mock.js"
    text = mock_path.read_text(encoding="utf-8")
    prods_js = "const PRODUCTS = " + json.dumps(products, indent=2) + ";"
    text, n1 = re.subn(r"const PRODUCTS = \[.*?\n  \];", lambda _: prods_js, text, flags=re.DOTALL)
    rev_inner = ",\n".join(
        f"    {pid}: ["
        + ", ".join(json.dumps(r) for r in rs)
        + "]"
        for pid, rs in _group_reviews(reviews).items()
    )
    rev_js = "const REVIEWS = {\n" + rev_inner + ",\n  };"
    text, n2 = re.subn(r"const REVIEWS = \{.*?\n  \};", lambda _: rev_js, text, flags=re.DOTALL)
    return text, n1, n2


def _group_reviews(reviews):
    grouped: dict[str, list] = {}
    for r in reviews:
        grouped.setdefault(r["product_id"], []).append(r)
    return grouped


def main() -> int:
    write = "--write" in sys.argv[1:]
    products = json.load(open(ROOT / "data" / "products.json", encoding="utf-8"))
    reviews = json.load(open(ROOT / "data" / "reviews.json", encoding="utf-8"))
    base_p, base_r = len(products), len(reviews)
    products = [p for p in products if p["product_id"] in {f"P{i:02d}" for i in range(1, 7)}]
    reviews = [r for r in reviews if r["review_id"] in {f"R{i:02d}" for i in range(1, 7)}]
    products = build_products(products)
    reviews = build_reviews(reviews)
    mock_text, n1, n2 = regen_mock(products, reviews)
    print(f"products: {base_p} -> {len(products)}; reviews: {base_r} -> {len(reviews)}; mock blocks: {n1}/{n2}")
    if not write:
        print("dry run (pass --write to apply)")
        return 0
    (ROOT / "data" / "products.json").write_text(dump_pretty(products), encoding="utf-8")
    (ROOT / "data" / "reviews.json").write_text(dump_pretty(reviews), encoding="utf-8")
    (ROOT / "app" / "static" / "mock.js").write_text(mock_text, encoding="utf-8")
    print("wrote data/products.json, data/reviews.json, app/static/mock.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
