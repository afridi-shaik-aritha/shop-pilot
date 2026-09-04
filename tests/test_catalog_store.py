# tests/test_catalog_store.py
from app.catalog.store import SqliteCatalogStore


def test_seed_from_json_and_decrement(tmp_path):
    store = SqliteCatalogStore(str(tmp_path / "c.db"))
    assert store.get_product("P01").stock == 42
    assert store.decrement_stock("P01", 1) is True
    assert store.get_product("P01").stock == 41
    assert store.decrement_stock("P01", 999) is False
    store.close()


def test_crud_roundtrip(tmp_path):
    from app.models import Product

    store = SqliteCatalogStore(str(tmp_path / "c.db"))
    p = store.get_product("P03")
    p.price = 1111.0
    p.stock = 50
    store.upsert_product(p)
    assert store.get_product("P03").price == 1111.0
    assert store.delete_product("P03") is True
    try:
        store.get_product("P03")
        assert False, "deleted product must raise"
    except Exception:
        pass
    store.upsert_product(p)
    assert store.get_product("P03").price == 1111.0
    store.close()


def test_reviews_crud(tmp_path):
    from app.models import Review

    store = SqliteCatalogStore(str(tmp_path / "c.db"))
    before = len(store.list_reviews())
    assert before > 0
    r = Review(review_id="RX-TEST", product_id="P01", rating=5, title="t", body="b")
    store.upsert_review(r)
    assert any(x.review_id == "RX-TEST" for x in store.list_reviews())
    assert store.delete_review("RX-TEST") is True
    store.close()


def test_seed_includes_p05_reviews(tmp_path):
    store = SqliteCatalogStore(str(tmp_path / "c.db"))
    ids = [r.product_id for r in store.list_reviews()]
    assert "P05" in ids
    store.close()
