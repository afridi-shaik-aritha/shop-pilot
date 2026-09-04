"""SQLite-backed stores (stdlib sqlite3, WAL mode, single local file).

Tables: sessions, idempotency keys, orders, traces. FileSessionStore remains
for fast unit tests; the API runtime uses this store.
"""
import json
import os
import sqlite3
import threading
import time

from app.state.models import Order, ShoppingSession

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS traces (
  run_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


class SqliteStore:
    def __init__(self, path: str) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)  # FastAPI worker threads
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        try:
            self._db.execute("PRAGMA journal_mode=WAL;")
            self._db.execute("PRAGMA busy_timeout=5000;")
        except sqlite3.Error:
            pass

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def save(self, session: ShoppingSession) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO sessions(session_id, user_id, payload, updated_at)"
                " VALUES(?,?,?,?)"
                " ON CONFLICT(session_id) DO UPDATE SET"
                " user_id=excluded.user_id, payload=excluded.payload,"
                " updated_at=excluded.updated_at",
                (session.session_id, session.user_id,
                 session.model_dump_json(), time.time()),
            )
            self._db.commit()

    def load(self, session_id: str) -> ShoppingSession:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            from app.checkout.service import SessionNotFound

            raise SessionNotFound(f"unknown session: {session_id}")
        return ShoppingSession.model_validate_json(row["payload"])

    def put_key(self, key: str, order_id: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO idempotency_keys(key, order_id, created_at)"
                " VALUES(?,?,?)",
                (key, order_id, time.time()),
            )
            self._db.commit()

    def get_order_id(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT order_id FROM idempotency_keys WHERE key=?", (key,)
            ).fetchone()
            return row["order_id"] if row is not None else None

    def save_order(self, order: Order) -> None:
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute(
                    "INSERT OR REPLACE INTO orders(order_id, payload, created_at)"
                    " VALUES(?,?,?)",
                    (order.order_id, order.model_dump_json(), time.time()),
                )
                self._db.execute(
                    "INSERT OR IGNORE INTO idempotency_keys(key, order_id, created_at)"
                    " VALUES(?,?,?)",
                    (order.idempotency_key, order.order_id, time.time()),
                )
                self._db.commit()
            except Exception:
                try:
                    self._db.rollback()
                except Exception:
                    pass
                raise

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM orders WHERE order_id=?", (order_id,)
            ).fetchone()
        if row is None:
            from app.checkout.service import OrderNotFound

            raise OrderNotFound(f"unknown order: {order_id}")
        return Order.model_validate_json(row["payload"])

    def get_order_by_key(self, key: str) -> Order | None:
        order_id = self.get_order_id(key)
        if order_id is None:
            return None
        return self.get_order(order_id)

    def save_trace(self, run_id: str, kind: str, payload: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO traces(run_id, kind, payload, created_at)"
                " VALUES(?,?,?,?)",
                (run_id, kind, json.dumps(payload, sort_keys=True), time.time()),
            )
            self._db.commit()

    def list_traces(self, kind: str | None = None, limit: int = 50) -> list[dict]:
        try:
            limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit = 50
        with self._lock:
            if kind is None:
                rows = self._db.execute(
                    "SELECT run_id, kind, payload FROM traces ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT run_id, kind, payload FROM traces WHERE kind=?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
        return [
            {"run_id": r["run_id"], "kind": r["kind"],
             "payload": json.loads(r["payload"])}
            for r in rows
        ]
