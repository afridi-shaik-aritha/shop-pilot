"""Authoritative catalog schemas. Prices are INR. Missing attributes use None, never invented text."""
from pydantic import BaseModel, Field


class Product(BaseModel):
    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    specs: dict = Field(default_factory=dict)
    price: float = Field(ge=0)
    rating: float = Field(ge=0, le=5)
    review_count: int = Field(ge=0)
    availability: bool = True
    stock: int = Field(ge=0)


class Review(BaseModel):
    review_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    rating: int = Field(ge=1, le=5)
    title: str = ""
    body: str = ""
    helpful_votes: int = Field(ge=0, default=0)
