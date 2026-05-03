from typing import List
from pydantic import BaseModel, Field
from app.store.schemas import ProductCard

class ChatResponse(BaseModel):
    reply_text: str
    products: List[ProductCard] = Field(default_factory=list)
    suggested_replies: List[str] = Field(default_factory=list)
