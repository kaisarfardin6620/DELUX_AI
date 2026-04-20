from typing import List, Optional

from pydantic import BaseModel, Field


class ProductCard(BaseModel):
    id: int
    title: str
    image_url: Optional[str]
    price: Optional[float]
    original_price: Optional[float]
    discount_percentage: Optional[float]
    platform_name: str
    external_url: Optional[str]
    condition: Optional[str]
    currency: Optional[str]
    free_shipping: Optional[bool]


class ChatResponse(BaseModel):
    reply_text: str
    products: List[ProductCard] = Field(default_factory=list)
