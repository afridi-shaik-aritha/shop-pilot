"""Environment-driven settings. Secrets come only from env and never enter traces."""
import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    products_path: str = "data/products.json"
    reviews_path: str = "data/reviews.json"
    top_k: int = 10
    db_path: str = "data/shop.db"
    llm_provider: str = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: int = 60
    retrieval_variant: str = "bm25"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_enabled: bool = False
    rerank_top_n: int = 20
    hybrid_rrf_k: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            products_path=os.getenv("ASA_PRODUCTS_PATH", "data/products.json"),
            reviews_path=os.getenv("ASA_REVIEWS_PATH", "data/reviews.json"),
            top_k=_int_env("ASA_TOP_K", 10),
            db_path=os.getenv("ASA_DB_PATH", "data/shop.db"),
            llm_provider=os.getenv("LLM_PROVIDER", "none"),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_timeout_s=_int_env("LLM_TIMEOUT_S", 60),
            retrieval_variant=os.getenv("ASA_RETRIEVAL", "bm25"),
            embedding_model=os.getenv(
                "ASA_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            rerank_model=os.getenv(
                "ASA_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            rerank_enabled=os.getenv("ASA_RERANK", "0").lower()
            in ("1", "true", "yes"),
            rerank_top_n=_int_env("ASA_RERANK_TOP_N", 20),
            hybrid_rrf_k=_int_env("ASA_RRF_K", 60),
        )

    def has_llm(self) -> bool:
        return self.llm_provider in ("nim", "openrouter") and bool(
            self.llm_base_url and self.llm_api_key and self.llm_model
        )


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE lines (later duplicates win) without overriding the real
    environment. Call this at app entrypoints (server boot, CLIs) so local
    `.env` files work; library callers keep pure env semantics. Secrets are
    never logged or traced."""
    if not os.path.exists(path):
        return
    parsed: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip inline comments only when outside quotes.
            cleaned: list[str] = []
            quote: str | None = None
            i = 0
            while i < len(value):
                ch = value[i]
                if quote is None and ch in ("#",):
                    # '#' starts a comment only when preceded by whitespace
                    if cleaned and cleaned[-1] in (" ", "\t"):
                        break
                    cleaned.append(ch)
                elif ch in ("'", '"'):
                    if quote is None:
                        quote = ch
                    elif quote == ch:
                        quote = None
                    else:
                        cleaned.append(ch)
                else:
                    cleaned.append(ch)
                i += 1
            value = "".join(cleaned).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key:
                parsed[key] = value
    for key, value in parsed.items():
        if key and key not in os.environ:
            os.environ[key] = value
