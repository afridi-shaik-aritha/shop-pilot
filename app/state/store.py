"""JSON file session store. Swap for a DB behind this interface in Plan 3."""
import json
import os

from app.state.models import ShoppingSession


class FileSessionStore:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, session_id: str) -> str:
        return os.path.join(self._base_dir, f"{session_id}.json")

    def save(self, session: ShoppingSession) -> None:
        with open(self._path(session.session_id), "w", encoding="utf-8") as f:
            f.write(session.model_dump_json())

    def load(self, session_id: str) -> ShoppingSession:
        path = self._path(session_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"unknown session: {session_id}")
        with open(path, encoding="utf-8") as f:
            return ShoppingSession.model_validate(json.load(f))
