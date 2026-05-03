from typing import Optional
from pydantic import BaseModel

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
