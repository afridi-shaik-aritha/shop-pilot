"""SQLite-backed catalog (products + reviews), seeded from JSON on first boot.

JSON files remain the version-controlled seed; SQLite is runtime truth so
orders can atomically decrement stock and admin CRUD persists.
"""
import json
import os
import sqlite3
import threading

from app.models import Product, Review

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (product_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (review_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL);
"""


class SqliteCatalogStore:
    def __init__(
        self,
        path: str,
        products_seed: str = "data/products.json",
        reviews_seed: str = "data/reviews.json",
    ) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        try:
            self._db.execute("PRAGMA journal_mode=WAL;")
            self._db.execute("PRAGMA busy_timeout=5000;")
        except sqlite3.Error:
            pass
        with self._lock:
            # INSERT OR IGNORE per id (not just when empty): upgrades pick up
            # new seed rows while never clobbering admin edits or stock levels.
            try:
                with open(products_seed, encoding="utf-8") as f:
                    items = json.load(f)
            except (OSError, ValueError):
                items = []
            for item in items:
                p = Product(**item)
                self._db.execute(
                    "INSERT OR IGNORE INTO products VALUES(?,?)",
                    (p.product_id, p.model_dump_json()),
                )
            try:
                with open(reviews_seed, encoding="utf-8") as f:
                    ritems = json.load(f)
            except (OSError, ValueError):
                ritems = []
            for item in ritems:
                r = Review(**item)
                self._db.execute(
                    "INSERT OR IGNORE INTO reviews VALUES(?,?,?)",
                    (r.review_id, r.product_id, r.model_dump_json()),
                )
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def list_products(self) -> list[Product]:
        with self._lock:
            rows = self._db.execute("SELECT payload FROM products").fetchall()
        return [Product.model_validate_json(r["payload"]) for r in rows]

    def get_product(self, product_id: str) -> Product:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM products WHERE product_id=?", (product_id,)
            ).fetchone()
        if row is None:
            from app.catalog.service import ProductNotFound

            raise ProductNotFound(f"unknown product: {product_id}")
        return Product.model_validate_json(row["payload"])

    def upsert_product(self, product: Product) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO products VALUES(?,?)",
                (product.product_id, product.model_dump_json()),
            )
            self._db.commit()

    def delete_product(self, product_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM products WHERE product_id=?", (product_id,)
            )
            self._db.commit()
            return cur.rowcount > 0

    def decrement_stock(self, product_id: str, qty: int) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM products WHERE product_id=?", (product_id,)
            ).fetchone()
            if row is None:
                return False
            p = Product.model_validate_json(row["payload"])
            if p.stock < qty:
                return False
            p.stock -= qty
            if p.stock <= 0:
                p.stock = 0
                p.availability = False
            self._db.execute(
                "UPDATE products SET payload=? WHERE product_id=?",
                (p.model_dump_json(), product_id),
            )
            self._db.commit()
            return True

    def list_reviews(self) -> list[Review]:
        with self._lock:
            rows = self._db.execute("SELECT payload FROM reviews").fetchall()
        return [Review.model_validate_json(r["payload"]) for r in rows]

    def category_counts(self) -> list[dict]:
        """Distinct categories with total + in-stock counts, alphabetical."""
        counts: dict[str, dict] = {}
        for p in self.list_products():
            row = counts.setdefault(p.category, {"category": p.category, "total": 0, "in_stock": 0})
            row["total"] += 1
            if p.availability and p.stock > 0:
                row["in_stock"] += 1
        return sorted(counts.values(), key=lambda r: r["category"])

    def upsert_review(self, review: Review) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO reviews VALUES(?,?,?)",
                (review.review_id, review.product_id, review.model_dump_json()),
            )
            self._db.commit()

    def delete_review(self, review_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM reviews WHERE review_id=?", (review_id,)
            )
            self._db.commit()
            return cur.rowcount > 0
