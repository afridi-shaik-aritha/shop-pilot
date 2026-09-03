"""Environment-driven settings. Secrets come only from env and never enter traces."""
import os
from dataclasses import dataclass


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

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            products_path=os.getenv("ASA_PRODUCTS_PATH", "data/products.json"),
            reviews_path=os.getenv("ASA_REVIEWS_PATH", "data/reviews.json"),
            top_k=int(os.getenv("ASA_TOP_K", "10")),
            db_path=os.getenv("ASA_DB_PATH", "data/shop.db"),
            llm_provider=os.getenv("LLM_PROVIDER", "none"),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_timeout_s=int(os.getenv("LLM_TIMEOUT_S", "60")),
        )

    def has_llm(self) -> bool:
        return self.llm_provider in ("nim", "openrouter") and bool(
            self.llm_base_url and self.llm_api_key and self.llm_model
        )
