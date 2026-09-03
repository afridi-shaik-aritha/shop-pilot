import pytest
from pydantic import ValidationError

from app.models import Product, Review


def test_product_accepts_full_record():
    p = Product(
        product_id="P01",
        name="SonicWave X5",
        brand="SonicWave",
        category="wireless headphones",
        description="Wireless over-ear headphones with long battery life.",
        specs={"battery_hours": 60, "weight_g": 254},
        price=8499.0,
        rating=4.4,
        review_count=2314,
        availability=True,
        stock=42,
    )
    assert p.product_id == "P01"
    assert p.specs["battery_hours"] == 60


def test_product_rejects_negative_price():
    with pytest.raises(ValidationError):
        Product(
            product_id="PX",
            name="Bad",
            brand="Bad",
            category="misc",
            description="Bad record.",
            price=-1.0,
            rating=4.0,
            review_count=0,
            availability=False,
            stock=0,
        )


def test_review_links_to_product():
    r = Review(
        review_id="R1",
        product_id="P01",
        rating=5,
        title="Great battery",
        body="Lasts a full week of office use.",
        helpful_votes=112,
    )
    assert r.product_id == "P01"
    assert r.rating == 5
