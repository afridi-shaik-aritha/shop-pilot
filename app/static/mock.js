/* Shop-Pilot offline demo API.
 * Installs a deterministic mock behind the exact fetch contract the real
 * backend serves, so the whole UI flow is walkable without a server
 * (file:// previews, ?mock=1). Activated by the app when /health is
 * unreachable — see app.js boot().
 */
(function () {
  const PRODUCTS = [
  {
    "availability": true,
    "brand": "SonicWave",
    "category": "wireless headphones",
    "description": "Wireless over-ear headphones with long 60-hour battery life and comfortable fit.",
    "name": "SonicWave X5 Wireless Headphones",
    "price": 8499.0,
    "product_id": "P01",
    "rating": 4.4,
    "review_count": 2314,
    "specs": {
      "battery_hours": 60,
      "bluetooth": "5.3",
      "weight_g": 254
    },
    "stock": 42
  },
  {
    "availability": true,
    "brand": "BassBoom",
    "category": "wireless headphones",
    "description": "Bass-heavy wireless headphones with active noise cancellation and 40-hour battery.",
    "name": "BassBoom Pro Wireless Headphones",
    "price": 12999.0,
    "product_id": "P02",
    "rating": 4.6,
    "review_count": 1871,
    "specs": {
      "battery_hours": 40,
      "bluetooth": "5.2",
      "weight_g": 281
    },
    "stock": 17
  },
  {
    "availability": true,
    "brand": "ClearTone",
    "category": "wired earphones",
    "description": "Budget wired in-ear earphones with microphone for calls.",
    "name": "ClearTone Wired Earphones",
    "price": 999.0,
    "product_id": "P03",
    "rating": 4.1,
    "review_count": 5420,
    "specs": {
      "weight_g": 18
    },
    "stock": 200
  },
  {
    "availability": true,
    "brand": "ThunderBox",
    "category": "bluetooth speaker",
    "description": "Portable bluetooth speaker with deep bass, 24-hour playtime and splash resistance.",
    "name": "ThunderBox Bluetooth Speaker",
    "price": 5999.0,
    "product_id": "P04",
    "rating": 4.5,
    "review_count": 3102,
    "specs": {
      "battery_hours": 24,
      "weight_g": 680
    },
    "stock": 63
  },
  {
    "availability": true,
    "brand": "PulseFit",
    "category": "smartwatch",
    "description": "Smartwatch with heart rate tracking, SpO2 sensor and 10-day battery.",
    "name": "PulseFit S2 Smartwatch",
    "price": 7999.0,
    "product_id": "P05",
    "rating": 4.3,
    "review_count": 1290,
    "specs": {
      "battery_days": 10,
      "weight_g": 36
    },
    "stock": 88
  },
  {
    "availability": false,
    "brand": "SonicWave",
    "category": "wireless headphones",
    "description": "Refurbished wireless headphones, same 60-hour battery, limited warranty.",
    "name": "SonicWave X5 Refurbished Unit",
    "price": 6499.0,
    "product_id": "P06",
    "rating": 4.0,
    "review_count": 412,
    "specs": {
      "battery_hours": 60,
      "weight_g": 254
    },
    "stock": 0
  },
  {
    "availability": true,
    "brand": "AudioNest",
    "category": "wireless headphones",
    "description": "Closed-back wireless headphones with hybrid noise cancellation and 45-hour playback on a single charge.",
    "name": "AudioNest Hush One Wireless Headphones",
    "price": 9999.0,
    "product_id": "P07",
    "rating": 4.3,
    "review_count": 864,
    "specs": {
      "battery_hours": 45,
      "bluetooth": "5.3",
      "weight_g": 262
    },
    "stock": 25
  },
  {
    "availability": true,
    "brand": "BeatCraft",
    "category": "wireless headphones",
    "description": "Flagship wireless headphones with studio-tuned drivers and plush memory-foam cushions.",
    "name": "BeatCraft Studio Max Wireless Headphones",
    "price": 14999.0,
    "product_id": "P08",
    "rating": 4.7,
    "review_count": 1204,
    "specs": {
      "battery_hours": 38,
      "bluetooth": "5.4",
      "weight_g": 295
    },
    "stock": 12
  },
  {
    "availability": true,
    "brand": "EchoPods",
    "category": "wireless headphones",
    "description": "Lightweight wireless headphones with punchy sound and fast charging \u2014 10 minutes gives 5 hours.",
    "name": "EchoPods Lite Wireless Headphones",
    "price": 4999.0,
    "product_id": "P09",
    "rating": 4.0,
    "review_count": 2310,
    "specs": {
      "battery_hours": 35,
      "bluetooth": "5.2",
      "weight_g": 210
    },
    "stock": 60
  },
  {
    "availability": false,
    "brand": "SoundLoom",
    "category": "wireless headphones",
    "description": "Foldable wireless headphones with multipoint pairing for laptop and phone.",
    "name": "SoundLoom Travel Wireless Headphones",
    "price": 7999.0,
    "product_id": "P10",
    "rating": 4.2,
    "review_count": 540,
    "specs": {
      "battery_hours": 40,
      "bluetooth": "5.3",
      "weight_g": 240
    },
    "stock": 0
  },
  {
    "availability": true,
    "brand": "RumbleBox",
    "category": "bluetooth speaker",
    "description": "Room-filling bluetooth speaker with thumping bass and LED light ring for house parties.",
    "name": "RumbleBox Party Bluetooth Speaker",
    "price": 8999.0,
    "product_id": "P11",
    "rating": 4.4,
    "review_count": 976,
    "specs": {
      "battery_hours": 18,
      "weight_g": 1200
    },
    "stock": 34
  },
  {
    "availability": true,
    "brand": "SoundCrest",
    "category": "bluetooth speaker",
    "description": "Pocket-size bluetooth speaker with clear mids and 12-hour playback for daily use.",
    "name": "SoundCrest Mini Bluetooth Speaker",
    "price": 2999.0,
    "product_id": "P12",
    "rating": 4.2,
    "review_count": 3420,
    "specs": {
      "battery_hours": 12,
      "weight_g": 340
    },
    "stock": 120
  },
  {
    "availability": true,
    "brand": "BassNest",
    "category": "bluetooth speaker",
    "description": "Rugged bluetooth speaker with deep bass radiator and IPX7 waterproofing for poolside days.",
    "name": "BassNest Outdoor Bluetooth Speaker",
    "price": 7499.0,
    "product_id": "P13",
    "rating": 4.5,
    "review_count": 689,
    "specs": {
      "battery_hours": 20,
      "weight_g": 820
    },
    "stock": 28
  },
  {
    "availability": true,
    "brand": "WristFit",
    "category": "smartwatch",
    "description": "AMOLED smartwatch with dual-band GPS, heart rate variability and 14-day battery.",
    "name": "WristFit GTR Smartwatch",
    "price": 10999.0,
    "product_id": "P14",
    "rating": 4.5,
    "review_count": 743,
    "specs": {
      "battery_days": 14,
      "weight_g": 42
    },
    "stock": 41
  },
  {
    "availability": true,
    "brand": "BeatBand",
    "category": "smartwatch",
    "description": "Slim smartwatch with all-day heart rate monitoring, step counting and 7-day battery.",
    "name": "BeatBand Active Smartwatch",
    "price": 4999.0,
    "product_id": "P15",
    "rating": 4.1,
    "review_count": 1876,
    "specs": {
      "battery_days": 7,
      "weight_g": 29
    },
    "stock": 95
  },
  {
    "availability": false,
    "brand": "OrbitWatch",
    "category": "smartwatch",
    "description": "Steel smartwatch with ECG, blood oxygen and wireless charging.",
    "name": "OrbitWatch Classic Smartwatch",
    "price": 14999.0,
    "product_id": "P16",
    "rating": 4.6,
    "review_count": 312,
    "specs": {
      "battery_days": 5,
      "weight_g": 58
    },
    "stock": 0
  },
  {
    "availability": true,
    "brand": "WireTune",
    "category": "wired earphones",
    "description": "Hi-res certified wired earphones with braided cable and in-line controls.",
    "name": "WireTune Pro Wired Earphones",
    "price": 1499.0,
    "product_id": "P17",
    "rating": 4.3,
    "review_count": 2874,
    "specs": {
      "weight_g": 22
    },
    "stock": 150
  },
  {
    "availability": true,
    "brand": "AudioPlug",
    "category": "wired earphones",
    "description": "Extra-bass wired earphones with snug fit for workouts.",
    "name": "AudioPlug Bass Wired Earphones",
    "price": 699.0,
    "product_id": "P18",
    "rating": 3.9,
    "review_count": 4102,
    "specs": {
      "weight_g": 16
    },
    "stock": 300
  },
  {
    "availability": true,
    "brand": "VoltBook",
    "category": "laptop",
    "description": "Thin 14-inch laptop with 16GB RAM, 512GB SSD and 18-hour battery for workdays.",
    "name": "VoltBook Air 14 Laptop",
    "price": 54990.0,
    "product_id": "P19",
    "rating": 4.5,
    "review_count": 689,
    "specs": {
      "ram_gb": 16,
      "storage_gb": 512,
      "weight_g": 1290
    },
    "stock": 22
  },
  {
    "availability": true,
    "brand": "VoltBook",
    "category": "laptop",
    "description": "Creator laptop with dedicated graphics, 32GB RAM and color-accurate display.",
    "name": "VoltBook Pro 16 Laptop",
    "price": 89990.0,
    "product_id": "P20",
    "rating": 4.7,
    "review_count": 412,
    "specs": {
      "ram_gb": 32,
      "storage_gb": 1024,
      "weight_g": 2100
    },
    "stock": 9
  },
  {
    "availability": true,
    "brand": "CompuPro",
    "category": "laptop",
    "description": "Everyday 15-inch laptop with backlit keyboard and fast charging.",
    "name": "CompuPro Everyday 15 Laptop",
    "price": 42990.0,
    "product_id": "P21",
    "rating": 4.2,
    "review_count": 1530,
    "specs": {
      "ram_gb": 8,
      "storage_gb": 512,
      "weight_g": 1750
    },
    "stock": 47
  },
  {
    "availability": true,
    "brand": "CompuPro",
    "category": "laptop",
    "description": "Affordable 14-inch laptop for students with all-day battery.",
    "name": "CompuPro Budget 14 Laptop",
    "price": 29990.0,
    "product_id": "P22",
    "rating": 3.9,
    "review_count": 2210,
    "specs": {
      "ram_gb": 8,
      "storage_gb": 256,
      "weight_g": 1490
    },
    "stock": 83
  },
  {
    "availability": true,
    "brand": "NovaMobile",
    "category": "smartphone",
    "description": "5G smartphone with 120Hz AMOLED display and 50MP camera.",
    "name": "NovaMobile X5 Smartphone",
    "price": 32999.0,
    "product_id": "P23",
    "rating": 4.4,
    "review_count": 1980,
    "specs": {
      "storage_gb": 128,
      "battery_mah": 5000
    },
    "stock": 56
  },
  {
    "availability": true,
    "brand": "NovaMobile",
    "category": "smartphone",
    "description": "Flagship smartphone with periscope zoom camera and titanium frame.",
    "name": "NovaMobile Ultra Smartphone",
    "price": 59999.0,
    "product_id": "P24",
    "rating": 4.6,
    "review_count": 870,
    "specs": {
      "storage_gb": 256,
      "battery_mah": 5400
    },
    "stock": 23
  },
  {
    "availability": true,
    "brand": "OrbitPhone",
    "category": "smartphone",
    "description": "Budget 5G smartphone with big battery and clean software.",
    "name": "OrbitPhone Lite Smartphone",
    "price": 15999.0,
    "product_id": "P25",
    "rating": 4.1,
    "review_count": 3120,
    "specs": {
      "storage_gb": 128,
      "battery_mah": 6000
    },
    "stock": 110
  },
  {
    "availability": true,
    "brand": "OrbitPhone",
    "category": "smartphone",
    "description": "Compact smartphone with one-hand friendly size and wireless charging.",
    "name": "OrbitPhone Mini Smartphone",
    "price": 24999.0,
    "product_id": "P26",
    "rating": 4.3,
    "review_count": 640,
    "specs": {
      "storage_gb": 128,
      "battery_mah": 4200
    },
    "stock": 38
  },
  {
    "availability": true,
    "brand": "SlatePro",
    "category": "tablet",
    "description": "11-inch tablet with stylus support and 12-hour battery for notes and art.",
    "name": "SlatePro 11 Tablet",
    "price": 38990.0,
    "product_id": "P27",
    "rating": 4.5,
    "review_count": 520,
    "specs": {
      "storage_gb": 128,
      "weight_g": 480
    },
    "stock": 31
  },
  {
    "availability": true,
    "brand": "TabNest",
    "category": "tablet",
    "description": "Kid-proof tablet with parental controls and bumper case.",
    "name": "TabNest Kids Tablet",
    "price": 12999.0,
    "product_id": "P28",
    "rating": 4.2,
    "review_count": 1430,
    "specs": {
      "storage_gb": 64,
      "weight_g": 550
    },
    "stock": 74
  },
  {
    "availability": true,
    "brand": "SlatePro",
    "category": "tablet",
    "description": "Large 13-inch tablet with desktop-class chip for video editing.",
    "name": "SlatePro Max 13 Tablet",
    "price": 64990.0,
    "product_id": "P29",
    "rating": 4.6,
    "review_count": 210,
    "specs": {
      "storage_gb": 256,
      "weight_g": 680
    },
    "stock": 14
  },
  {
    "availability": true,
    "brand": "KeyForge",
    "category": "mechanical keyboard",
    "description": "Hot-swappable mechanical keyboard with tactile switches and PBT keycaps.",
    "name": "KeyForge TKL Mechanical Keyboard",
    "price": 7999.0,
    "product_id": "P30",
    "rating": 4.6,
    "review_count": 930,
    "specs": {
      "keys": 87
    },
    "stock": 52
  },
  {
    "availability": true,
    "brand": "ClickClack",
    "category": "mechanical keyboard",
    "description": "Compact 60 percent mechanical keyboard with linear switches and RGB.",
    "name": "ClickClack 60 Mechanical Keyboard",
    "price": 5999.0,
    "product_id": "P31",
    "rating": 4.4,
    "review_count": 1260,
    "specs": {
      "keys": 61
    },
    "stock": 68
  },
  {
    "availability": false,
    "brand": "KeyForge",
    "category": "mechanical keyboard",
    "description": "Wireless mechanical keyboard with 2.4GHz and triple Bluetooth pairing.",
    "name": "KeyForge Wireless Mechanical Keyboard",
    "price": 9999.0,
    "product_id": "P32",
    "rating": 4.5,
    "review_count": 410,
    "specs": {
      "keys": 98,
      "battery_hours": 200
    },
    "stock": 0
  },
  {
    "availability": true,
    "brand": "GlidePro",
    "category": "wireless mouse",
    "description": "Silent-click wireless mouse with ergonomic shape for office work.",
    "name": "GlidePro Silent Wireless Mouse",
    "price": 1999.0,
    "product_id": "P33",
    "rating": 4.3,
    "review_count": 2870,
    "specs": {
      "dpi": 3200
    },
    "stock": 140
  },
  {
    "availability": true,
    "brand": "SwiftClick",
    "category": "wireless mouse",
    "description": "Esports-grade wireless mouse with 26000 DPI sensor and 90-hour battery.",
    "name": "SwiftClick Gaming Wireless Mouse",
    "price": 4999.0,
    "product_id": "P34",
    "rating": 4.6,
    "review_count": 1150,
    "specs": {
      "dpi": 26000,
      "battery_hours": 90
    },
    "stock": 47
  },
  {
    "availability": true,
    "brand": "GlidePro",
    "category": "wireless mouse",
    "description": "Slim wireless mouse that slips into a laptop sleeve.",
    "name": "GlidePro Travel Wireless Mouse",
    "price": 1499.0,
    "product_id": "P35",
    "rating": 4.1,
    "review_count": 1980,
    "specs": {
      "dpi": 1600
    },
    "stock": 190
  },
  {
    "availability": true,
    "brand": "ViewMax",
    "category": "monitor",
    "description": "27-inch 4K monitor with HDR and height-adjustable stand.",
    "name": "ViewMax 27 4K Monitor",
    "price": 32999.0,
    "product_id": "P36",
    "rating": 4.5,
    "review_count": 480,
    "specs": {
      "size_in": 27
    },
    "stock": 26
  },
  {
    "availability": true,
    "brand": "ClearPanel",
    "category": "monitor",
    "description": "Eye-care 24-inch monitor with low blue light for long workdays.",
    "name": "ClearPanel 24 Office Monitor",
    "price": 13999.0,
    "product_id": "P37",
    "rating": 4.3,
    "review_count": 1120,
    "specs": {
      "size_in": 24
    },
    "stock": 58
  },
  {
    "availability": true,
    "brand": "ViewMax",
    "category": "monitor",
    "description": "Curved 34-inch ultrawide monitor with 144Hz refresh for gaming.",
    "name": "ViewMax 34 Ultrawide Monitor",
    "price": 54999.0,
    "product_id": "P38",
    "rating": 4.7,
    "review_count": 230,
    "specs": {
      "size_in": 34
    },
    "stock": 11
  },
  {
    "availability": true,
    "brand": "LensCraft",
    "category": "mirrorless camera",
    "description": "24MP mirrorless camera with 4K video and in-body stabilization.",
    "name": "LensCraft M50 Mirrorless Camera",
    "price": 64990.0,
    "product_id": "P39",
    "rating": 4.6,
    "review_count": 340,
    "specs": {
      "megapixels": 24
    },
    "stock": 16
  },
  {
    "availability": true,
    "brand": "FotoPro",
    "category": "instant camera",
    "description": "Point-and-shoot instant camera with auto exposure for parties.",
    "name": "FotoPro Instant Camera",
    "price": 8999.0,
    "product_id": "P40",
    "rating": 4.2,
    "review_count": 1740,
    "specs": {
      "megapixels": 12
    },
    "stock": 92
  },
  {
    "availability": true,
    "brand": "LensCraft",
    "category": "mirrorless camera",
    "description": "Full-frame mirrorless camera with dual card slots for professionals.",
    "name": "LensCraft Pro Mirrorless Camera",
    "price": 129990.0,
    "product_id": "P41",
    "rating": 4.8,
    "review_count": 120,
    "specs": {
      "megapixels": 33
    },
    "stock": 6
  },
  {
    "availability": true,
    "brand": "TrailPack",
    "category": "backpack",
    "description": "45-litre hiking backpack with rain cover and ventilated back.",
    "name": "TrailPack 45 Hiking Backpack",
    "price": 4999.0,
    "product_id": "P42",
    "rating": 4.5,
    "review_count": 860,
    "specs": {
      "capacity_l": 45
    },
    "stock": 73
  },
  {
    "availability": false,
    "brand": "UrbanHaul",
    "category": "backpack",
    "description": "Water-repellent laptop backpack with USB passthrough and 15-inch sleeve.",
    "name": "UrbanHaul Laptop Backpack",
    "price": 2999.0,
    "product_id": "P43",
    "rating": 4.4,
    "review_count": 2130,
    "specs": {
      "capacity_l": 25
    },
    "stock": 0
  },
  {
    "availability": true,
    "brand": "TrailPack",
    "category": "backpack",
    "description": "Light 20-litre daypack backpack for commutes and short trails.",
    "name": "TrailPack Daypack 20 Backpack",
    "price": 1999.0,
    "product_id": "P44",
    "rating": 4.3,
    "review_count": 1470,
    "specs": {
      "capacity_l": 20
    },
    "stock": 120
  },
  {
    "availability": true,
    "brand": "StrideX",
    "category": "running shoes",
    "description": "Carbon-plated running shoes with responsive foam for race day.",
    "name": "StrideX Marathon Running Shoes",
    "price": 8999.0,
    "product_id": "P45",
    "rating": 4.6,
    "review_count": 790,
    "specs": {
      "weight_g": 220
    },
    "stock": 44
  },
  {
    "availability": true,
    "brand": "RunFlex",
    "category": "running shoes",
    "description": "Cushioned daily running shoes with breathable knit upper.",
    "name": "RunFlex Daily Running Shoes",
    "price": 5999.0,
    "product_id": "P46",
    "rating": 4.4,
    "review_count": 1680,
    "specs": {
      "weight_g": 280
    },
    "stock": 87
  },
  {
    "availability": true,
    "brand": "StrideX",
    "category": "running shoes",
    "description": "Grippy trail running shoes with rock plate for uneven paths.",
    "name": "StrideX Trail Running Shoes",
    "price": 7499.0,
    "product_id": "P47",
    "rating": 4.5,
    "review_count": 530,
    "specs": {
      "weight_g": 310
    },
    "stock": 39
  },
  {
    "availability": true,
    "brand": "BrewMate",
    "category": "coffee maker",
    "description": "12-cup drip coffee maker with programmable timer and thermal carafe.",
    "name": "BrewMate Drip Coffee Maker",
    "price": 4999.0,
    "product_id": "P48",
    "rating": 4.3,
    "review_count": 920,
    "specs": {
      "capacity_cups": 12
    },
    "stock": 51
  },
  {
    "availability": true,
    "brand": "CafePress",
    "category": "coffee maker",
    "description": "Espresso coffee maker with steam wand for lattes at home.",
    "name": "CafePress Espresso Coffee Maker",
    "price": 18999.0,
    "product_id": "P49",
    "rating": 4.6,
    "review_count": 380,
    "specs": {
      "pressure_bar": 15
    },
    "stock": 19
  },
  {
    "availability": true,
    "brand": "BrewMate",
    "category": "coffee maker",
    "description": "Classic French press coffee maker with stainless filter.",
    "name": "BrewMate French Press Coffee Maker",
    "price": 1499.0,
    "product_id": "P50",
    "rating": 4.4,
    "review_count": 2310,
    "specs": {
      "capacity_cups": 8
    },
    "stock": 160
  }
];
  const REVIEWS = {
    P01: [{"body": "Easily lasts my full work week. Comfortable for long calls.", "helpful_votes": 112, "product_id": "P01", "rating": 5, "review_id": "R01", "title": "Battery for days"}, {"body": "Sound is clear, app equalizer helps. Case feels cheap.", "helpful_votes": 45, "product_id": "P01", "rating": 4, "review_id": "R02", "title": "Good value"}],
    P02: [{"body": "Noise cancellation is excellent on flights.", "helpful_votes": 89, "product_id": "P02", "rating": 5, "review_id": "R03", "title": "Bass monster"}],
    P04: [{"body": "Deep bass for the size, battery survives full-day picnics.", "helpful_votes": 61, "product_id": "P04", "rating": 4, "review_id": "R04", "title": "Loud and clear"}],
    P05: [{"body": "Compared against my chest strap on runs \u2014 within 2 bpm. The 10-day battery claim holds with always-on heart-rate tracking.", "helpful_votes": 84, "product_id": "P05", "rating": 5, "review_id": "R05", "title": "Heart-rate tracking is spot on"}, {"body": "SpO2 and sleep tracking work well and sync is fast. Wish the screen were brighter outdoors.", "helpful_votes": 41, "product_id": "P05", "rating": 4, "review_id": "R06", "title": "Great value tracker"}],
    P07: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Closed-back wireless headphones.", "helpful_votes": 55, "product_id": "P07", "rating": 4, "review_id": "R07", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Closed-back wireless headphones.", "helpful_votes": 76, "product_id": "P07", "rating": 5, "review_id": "R08", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Closed-back wireless headphones.", "helpful_votes": 68, "product_id": "P07", "rating": 3, "review_id": "R09", "title": "Good, minor quibbles"}],
    P08: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Flagship wireless headphones.", "helpful_votes": 130, "product_id": "P08", "rating": 5, "review_id": "R10", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Flagship wireless headphones.", "helpful_votes": 7, "product_id": "P08", "rating": 5, "review_id": "R11", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Flagship wireless headphones.", "helpful_votes": 177, "product_id": "P08", "rating": 5, "review_id": "R12", "title": "Exceeded expectations"}],
    P09: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Lightweight wireless headphones.", "helpful_votes": 195, "product_id": "P09", "rating": 4, "review_id": "R13", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Lightweight wireless headphones.", "helpful_votes": 137, "product_id": "P09", "rating": 5, "review_id": "R14", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Lightweight wireless headphones.", "helpful_votes": 62, "product_id": "P09", "rating": 4, "review_id": "R15", "title": "Good, minor quibbles"}],
    P10: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Foldable wireless headphones.", "helpful_votes": 75, "product_id": "P10", "rating": 3, "review_id": "R16", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Foldable wireless headphones.", "helpful_votes": 179, "product_id": "P10", "rating": 4, "review_id": "R17", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Foldable wireless headphones.", "helpful_votes": 27, "product_id": "P10", "rating": 4, "review_id": "R18", "title": "Exceeded expectations"}],
    P11: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Room-filling bluetooth speaker.", "helpful_votes": 83, "product_id": "P11", "rating": 4, "review_id": "R19", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Room-filling bluetooth speaker.", "helpful_votes": 180, "product_id": "P11", "rating": 5, "review_id": "R20", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Room-filling bluetooth speaker.", "helpful_votes": 55, "product_id": "P11", "rating": 4, "review_id": "R21", "title": "Good, minor quibbles"}],
    P12: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Pocket-size bluetooth speaker.", "helpful_votes": 73, "product_id": "P12", "rating": 5, "review_id": "R22", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Pocket-size bluetooth speaker.", "helpful_votes": 50, "product_id": "P12", "rating": 4, "review_id": "R23", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Pocket-size bluetooth speaker.", "helpful_votes": 170, "product_id": "P12", "rating": 3, "review_id": "R24", "title": "Exceeded expectations"}],
    P13: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Rugged bluetooth speaker.", "helpful_votes": 153, "product_id": "P13", "rating": 4, "review_id": "R25", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Rugged bluetooth speaker.", "helpful_votes": 73, "product_id": "P13", "rating": 5, "review_id": "R26", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Rugged bluetooth speaker.", "helpful_votes": 36, "product_id": "P13", "rating": 4, "review_id": "R27", "title": "Good, minor quibbles"}],
    P14: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. AMOLED smartwatch.", "helpful_votes": 148, "product_id": "P14", "rating": 5, "review_id": "R28", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. AMOLED smartwatch.", "helpful_votes": 8, "product_id": "P14", "rating": 5, "review_id": "R29", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. AMOLED smartwatch.", "helpful_votes": 17, "product_id": "P14", "rating": 4, "review_id": "R30", "title": "Exceeded expectations"}],
    P15: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Slim smartwatch.", "helpful_votes": 142, "product_id": "P15", "rating": 5, "review_id": "R31", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Slim smartwatch.", "helpful_votes": 137, "product_id": "P15", "rating": 3, "review_id": "R32", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Slim smartwatch.", "helpful_votes": 165, "product_id": "P15", "rating": 4, "review_id": "R33", "title": "Good, minor quibbles"}],
    P16: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Steel smartwatch.", "helpful_votes": 116, "product_id": "P16", "rating": 5, "review_id": "R34", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Steel smartwatch.", "helpful_votes": 69, "product_id": "P16", "rating": 5, "review_id": "R35", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Steel smartwatch.", "helpful_votes": 75, "product_id": "P16", "rating": 5, "review_id": "R36", "title": "Exceeded expectations"}],
    P17: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Hi-res certified wired earphones.", "helpful_votes": 29, "product_id": "P17", "rating": 4, "review_id": "R37", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Hi-res certified wired earphones.", "helpful_votes": 75, "product_id": "P17", "rating": 5, "review_id": "R38", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Hi-res certified wired earphones.", "helpful_votes": 91, "product_id": "P17", "rating": 3, "review_id": "R39", "title": "Good, minor quibbles"}],
    P18: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Extra-bass wired earphones.", "helpful_votes": 123, "product_id": "P18", "rating": 4, "review_id": "R40", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Extra-bass wired earphones.", "helpful_votes": 133, "product_id": "P18", "rating": 3, "review_id": "R41", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Extra-bass wired earphones.", "helpful_votes": 92, "product_id": "P18", "rating": 4, "review_id": "R42", "title": "Exceeded expectations"}],
    P19: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Thin 14-inch laptop.", "helpful_votes": 60, "product_id": "P19", "rating": 4, "review_id": "R43", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Thin 14-inch laptop.", "helpful_votes": 190, "product_id": "P19", "rating": 5, "review_id": "R44", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Thin 14-inch laptop.", "helpful_votes": 96, "product_id": "P19", "rating": 5, "review_id": "R45", "title": "Good, minor quibbles"}],
    P20: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Creator laptop.", "helpful_votes": 55, "product_id": "P20", "rating": 4, "review_id": "R46", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Creator laptop.", "helpful_votes": 147, "product_id": "P20", "rating": 5, "review_id": "R47", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Creator laptop.", "helpful_votes": 108, "product_id": "P20", "rating": 5, "review_id": "R48", "title": "Exceeded expectations"}],
    P21: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Everyday 15-inch laptop.", "helpful_votes": 154, "product_id": "P21", "rating": 4, "review_id": "R49", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Everyday 15-inch laptop.", "helpful_votes": 38, "product_id": "P21", "rating": 4, "review_id": "R50", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Everyday 15-inch laptop.", "helpful_votes": 104, "product_id": "P21", "rating": 4, "review_id": "R51", "title": "Good, minor quibbles"}],
    P22: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Affordable 14-inch laptop for students.", "helpful_votes": 12, "product_id": "P22", "rating": 5, "review_id": "R52", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Affordable 14-inch laptop for students.", "helpful_votes": 171, "product_id": "P22", "rating": 4, "review_id": "R53", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Affordable 14-inch laptop for students.", "helpful_votes": 148, "product_id": "P22", "rating": 3, "review_id": "R54", "title": "Exceeded expectations"}],
    P23: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. 5G smartphone.", "helpful_votes": 134, "product_id": "P23", "rating": 3, "review_id": "R55", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. 5G smartphone.", "helpful_votes": 40, "product_id": "P23", "rating": 3, "review_id": "R56", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. 5G smartphone.", "helpful_votes": 49, "product_id": "P23", "rating": 4, "review_id": "R57", "title": "Good, minor quibbles"}],
    P24: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Flagship smartphone.", "helpful_votes": 126, "product_id": "P24", "rating": 5, "review_id": "R58", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Flagship smartphone.", "helpful_votes": 173, "product_id": "P24", "rating": 5, "review_id": "R59", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Flagship smartphone.", "helpful_votes": 177, "product_id": "P24", "rating": 5, "review_id": "R60", "title": "Exceeded expectations"}],
    P25: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Budget 5G smartphone.", "helpful_votes": 131, "product_id": "P25", "rating": 4, "review_id": "R61", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Budget 5G smartphone.", "helpful_votes": 96, "product_id": "P25", "rating": 3, "review_id": "R62", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Budget 5G smartphone.", "helpful_votes": 87, "product_id": "P25", "rating": 4, "review_id": "R63", "title": "Good, minor quibbles"}],
    P26: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Compact smartphone.", "helpful_votes": 26, "product_id": "P26", "rating": 5, "review_id": "R64", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Compact smartphone.", "helpful_votes": 161, "product_id": "P26", "rating": 5, "review_id": "R65", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Compact smartphone.", "helpful_votes": 157, "product_id": "P26", "rating": 4, "review_id": "R66", "title": "Exceeded expectations"}],
    P27: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. 11-inch tablet.", "helpful_votes": 18, "product_id": "P27", "rating": 4, "review_id": "R67", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. 11-inch tablet.", "helpful_votes": 52, "product_id": "P27", "rating": 5, "review_id": "R68", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. 11-inch tablet.", "helpful_votes": 9, "product_id": "P27", "rating": 3, "review_id": "R69", "title": "Good, minor quibbles"}],
    P28: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Kid-proof tablet.", "helpful_votes": 65, "product_id": "P28", "rating": 4, "review_id": "R70", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Kid-proof tablet.", "helpful_votes": 148, "product_id": "P28", "rating": 4, "review_id": "R71", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Kid-proof tablet.", "helpful_votes": 106, "product_id": "P28", "rating": 3, "review_id": "R72", "title": "Exceeded expectations"}],
    P29: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Large 13-inch tablet.", "helpful_votes": 7, "product_id": "P29", "rating": 5, "review_id": "R73", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Large 13-inch tablet.", "helpful_votes": 37, "product_id": "P29", "rating": 4, "review_id": "R74", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Large 13-inch tablet.", "helpful_votes": 65, "product_id": "P29", "rating": 5, "review_id": "R75", "title": "Good, minor quibbles"}],
    P30: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Hot-swappable mechanical keyboard.", "helpful_votes": 97, "product_id": "P30", "rating": 5, "review_id": "R76", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Hot-swappable mechanical keyboard.", "helpful_votes": 36, "product_id": "P30", "rating": 5, "review_id": "R77", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Hot-swappable mechanical keyboard.", "helpful_votes": 5, "product_id": "P30", "rating": 5, "review_id": "R78", "title": "Exceeded expectations"}],
    P31: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Compact 60 percent mechanical keyboard.", "helpful_votes": 131, "product_id": "P31", "rating": 4, "review_id": "R79", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Compact 60 percent mechanical keyboard.", "helpful_votes": 14, "product_id": "P31", "rating": 4, "review_id": "R80", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Compact 60 percent mechanical keyboard.", "helpful_votes": 94, "product_id": "P31", "rating": 4, "review_id": "R81", "title": "Good, minor quibbles"}],
    P32: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Wireless mechanical keyboard.", "helpful_votes": 56, "product_id": "P32", "rating": 3, "review_id": "R82", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Wireless mechanical keyboard.", "helpful_votes": 185, "product_id": "P32", "rating": 4, "review_id": "R83", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Wireless mechanical keyboard.", "helpful_votes": 16, "product_id": "P32", "rating": 3, "review_id": "R84", "title": "Exceeded expectations"}],
    P33: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Silent-click wireless mouse.", "helpful_votes": 135, "product_id": "P33", "rating": 4, "review_id": "R85", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Silent-click wireless mouse.", "helpful_votes": 8, "product_id": "P33", "rating": 5, "review_id": "R86", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Silent-click wireless mouse.", "helpful_votes": 200, "product_id": "P33", "rating": 4, "review_id": "R87", "title": "Good, minor quibbles"}],
    P34: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Esports-grade wireless mouse.", "helpful_votes": 150, "product_id": "P34", "rating": 5, "review_id": "R88", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Esports-grade wireless mouse.", "helpful_votes": 176, "product_id": "P34", "rating": 5, "review_id": "R89", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Esports-grade wireless mouse.", "helpful_votes": 111, "product_id": "P34", "rating": 5, "review_id": "R90", "title": "Exceeded expectations"}],
    P35: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Slim wireless mouse that slips into a laptop sleeve.", "helpful_votes": 40, "product_id": "P35", "rating": 5, "review_id": "R91", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Slim wireless mouse that slips into a laptop sleeve.", "helpful_votes": 68, "product_id": "P35", "rating": 4, "review_id": "R92", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Slim wireless mouse that slips into a laptop sleeve.", "helpful_votes": 166, "product_id": "P35", "rating": 3, "review_id": "R93", "title": "Good, minor quibbles"}],
    P36: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. 27-inch 4K monitor.", "helpful_votes": 69, "product_id": "P36", "rating": 4, "review_id": "R94", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. 27-inch 4K monitor.", "helpful_votes": 13, "product_id": "P36", "rating": 5, "review_id": "R95", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. 27-inch 4K monitor.", "helpful_votes": 9, "product_id": "P36", "rating": 5, "review_id": "R96", "title": "Exceeded expectations"}],
    P37: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Eye-care 24-inch monitor.", "helpful_votes": 25, "product_id": "P37", "rating": 4, "review_id": "R97", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Eye-care 24-inch monitor.", "helpful_votes": 152, "product_id": "P37", "rating": 4, "review_id": "R98", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Eye-care 24-inch monitor.", "helpful_votes": 111, "product_id": "P37", "rating": 4, "review_id": "R99", "title": "Good, minor quibbles"}],
    P38: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Curved 34-inch ultrawide monitor.", "helpful_votes": 116, "product_id": "P38", "rating": 5, "review_id": "R100", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Curved 34-inch ultrawide monitor.", "helpful_votes": 190, "product_id": "P38", "rating": 5, "review_id": "R101", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Curved 34-inch ultrawide monitor.", "helpful_votes": 45, "product_id": "P38", "rating": 4, "review_id": "R102", "title": "Exceeded expectations"}],
    P39: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. 24MP mirrorless camera.", "helpful_votes": 128, "product_id": "P39", "rating": 5, "review_id": "R103", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. 24MP mirrorless camera.", "helpful_votes": 108, "product_id": "P39", "rating": 4, "review_id": "R104", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. 24MP mirrorless camera.", "helpful_votes": 112, "product_id": "P39", "rating": 5, "review_id": "R105", "title": "Good, minor quibbles"}],
    P40: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Point-and-shoot instant camera.", "helpful_votes": 157, "product_id": "P40", "rating": 5, "review_id": "R106", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Point-and-shoot instant camera.", "helpful_votes": 20, "product_id": "P40", "rating": 5, "review_id": "R107", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Point-and-shoot instant camera.", "helpful_votes": 166, "product_id": "P40", "rating": 5, "review_id": "R108", "title": "Exceeded expectations"}],
    P41: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Full-frame mirrorless camera.", "helpful_votes": 42, "product_id": "P41", "rating": 5, "review_id": "R109", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Full-frame mirrorless camera.", "helpful_votes": 9, "product_id": "P41", "rating": 5, "review_id": "R110", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Full-frame mirrorless camera.", "helpful_votes": 152, "product_id": "P41", "rating": 5, "review_id": "R111", "title": "Good, minor quibbles"}],
    P42: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. 45-litre hiking backpack.", "helpful_votes": 188, "product_id": "P42", "rating": 4, "review_id": "R112", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. 45-litre hiking backpack.", "helpful_votes": 41, "product_id": "P42", "rating": 5, "review_id": "R113", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. 45-litre hiking backpack.", "helpful_votes": 99, "product_id": "P42", "rating": 5, "review_id": "R114", "title": "Exceeded expectations"}],
    P43: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Water-repellent laptop backpack.", "helpful_votes": 96, "product_id": "P43", "rating": 3, "review_id": "R115", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Water-repellent laptop backpack.", "helpful_votes": 188, "product_id": "P43", "rating": 4, "review_id": "R116", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Water-repellent laptop backpack.", "helpful_votes": 198, "product_id": "P43", "rating": 4, "review_id": "R117", "title": "Good, minor quibbles"}],
    P44: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Light 20-litre daypack backpack for commutes and short trails.", "helpful_votes": 113, "product_id": "P44", "rating": 4, "review_id": "R118", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Light 20-litre daypack backpack for commutes and short trails.", "helpful_votes": 179, "product_id": "P44", "rating": 4, "review_id": "R119", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Light 20-litre daypack backpack for commutes and short trails.", "helpful_votes": 182, "product_id": "P44", "rating": 5, "review_id": "R120", "title": "Exceeded expectations"}],
    P45: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Carbon-plated running shoes.", "helpful_votes": 17, "product_id": "P45", "rating": 5, "review_id": "R121", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Carbon-plated running shoes.", "helpful_votes": 69, "product_id": "P45", "rating": 4, "review_id": "R122", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Carbon-plated running shoes.", "helpful_votes": 191, "product_id": "P45", "rating": 5, "review_id": "R123", "title": "Good, minor quibbles"}],
    P46: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Cushioned daily running shoes.", "helpful_votes": 25, "product_id": "P46", "rating": 4, "review_id": "R124", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Cushioned daily running shoes.", "helpful_votes": 140, "product_id": "P46", "rating": 5, "review_id": "R125", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Cushioned daily running shoes.", "helpful_votes": 186, "product_id": "P46", "rating": 4, "review_id": "R126", "title": "Exceeded expectations"}],
    P47: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Grippy trail running shoes.", "helpful_votes": 7, "product_id": "P47", "rating": 4, "review_id": "R127", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Grippy trail running shoes.", "helpful_votes": 85, "product_id": "P47", "rating": 4, "review_id": "R128", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Grippy trail running shoes.", "helpful_votes": 109, "product_id": "P47", "rating": 5, "review_id": "R129", "title": "Good, minor quibbles"}],
    P48: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. 12-cup drip coffee maker.", "helpful_votes": 35, "product_id": "P48", "rating": 4, "review_id": "R130", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. 12-cup drip coffee maker.", "helpful_votes": 134, "product_id": "P48", "rating": 4, "review_id": "R131", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. 12-cup drip coffee maker.", "helpful_votes": 67, "product_id": "P48", "rating": 4, "review_id": "R132", "title": "Exceeded expectations"}],
    P49: [{"body": "Does exactly what it promises. Delivery was quick and packaging was neat. Espresso coffee maker.", "helpful_votes": 170, "product_id": "P49", "rating": 5, "review_id": "R133", "title": "Great for the price"}, {"body": "Works great so far. A couple of small quirks but nothing that bothers me day to day. Espresso coffee maker.", "helpful_votes": 184, "product_id": "P49", "rating": 5, "review_id": "R134", "title": "Solid pick"}, {"body": "Performance matches the description. Would buy again without hesitation. Espresso coffee maker.", "helpful_votes": 76, "product_id": "P49", "rating": 5, "review_id": "R135", "title": "Good, minor quibbles"}],
    P50: [{"body": "Bought a second one as a gift after using mine for a month. Highly recommended. Classic French press coffee maker.", "helpful_votes": 124, "product_id": "P50", "rating": 4, "review_id": "R136", "title": "Very happy"}, {"body": "Build quality feels premium for this price. Setup took minutes and daily use has been flawless. Classic French press coffee maker.", "helpful_votes": 62, "product_id": "P50", "rating": 4, "review_id": "R137", "title": "Does the job well"}, {"body": "A noticeable upgrade over my old one. The attention to detail really shows. Classic French press coffee maker.", "helpful_votes": 78, "product_id": "P50", "rating": 3, "review_id": "R138", "title": "Exceeded expectations"}],
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

      if (path === "/categories" && method === "GET") {        const counts = {};
        for (const p of PRODUCTS) {
          const row = counts[p.category] || (counts[p.category] = { category: p.category, total: 0, in_stock: 0 });
          row.total += 1;
          if (p.availability && p.stock > 0) row.in_stock += 1;
        }
        return http(200, { categories: Object.values(counts).sort((a, b) => a.category.localeCompare(b.category)) });
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

      // A pending slip belongs to the exact trolley it was cut for: any cart
      // change voids it (mirrors the real API), so the UI can never show a
      // token for a trolley that no longer matches.
      const dropStaleSlip = () => {
        if (checkout && checkout.status === "AWAITING_CONFIRMATION") checkout = null;
      };

      if (path === "/cart" && method === "DELETE") {
        session.items = [];
        dropStaleSlip();
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
          dropStaleSlip();
          return http(200, { session_id: session.id, ...cartPayload() });
        }
        if (method === "DELETE") {
          session.items = session.items.filter((i) => i.product_id !== pid);
          dropStaleSlip();
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
        dropStaleSlip();
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

      if (path === "/products" && method === "GET") {
        return http(200, { products: PRODUCTS });
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
