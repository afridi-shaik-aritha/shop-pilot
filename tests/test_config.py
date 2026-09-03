from app.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.products_path == "data/products.json"
    assert s.reviews_path == "data/reviews.json"
    assert s.top_k == 10


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ASA_TOP_K", "3")
    monkeypatch.setenv("ASA_PRODUCTS_PATH", "data/custom.json")
    s = Settings.from_env()
    assert s.top_k == 3
    assert s.products_path == "data/custom.json"
