import base64
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.services import openai_client
from app.core.database import get_db
from app.media_api.services import build_image_url
from app.store.models import Platform, Product, ProductListing
from app.store.schemas import ProductCard
from app.store.services import search_products_in_db

router = APIRouter(prefix="/api/store", tags=["store"])


@router.get("/products/{product_id}/compare", response_model=List[ProductCard])
async def compare_product_prices(product_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(Product, ProductListing, Platform)
        .join(ProductListing, Product.id == ProductListing.product_id)
        .join(Platform, ProductListing.platform_id == Platform.id)
        .where(Product.id == product_id)
        .where(ProductListing.is_available == True)
        .order_by(ProductListing.price.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    products = []
    for prod, listing, platform in rows:
        products.append(
            ProductCard(
                id=prod.id,
                title=prod.title,
                image_url=build_image_url(prod.main_image),
                price=float(listing.price) if listing.price is not None else None,
                original_price=float(listing.original_price) if listing.original_price is not None else None,
                discount_percentage=float(listing.discount_percentage) if listing.discount_percentage is not None else None,
                platform_name=platform.name,
                external_url=listing.external_url,
                condition=listing.condition,
                currency=listing.currency,
                free_shipping=listing.free_shipping,
            )
        )
    return products



@router.post("/visual-search", response_model=List[ProductCard])
async def visual_search(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid image type. Only JPEG, PNG, and WebP are supported.")

    contents = await file.read()
    base64_image = base64.b64encode(contents).decode("utf-8")

    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Identify the specific brand and product model in this image. Reply ONLY with a short search keyword, for example 'Bose QuietComfort 45' or 'Nike Air Zoom Pegasus 39'."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{file.content_type};base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=50,
            timeout=config.OPENAI_TIMEOUT_SECONDS,
        )
        search_keyword = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Vision error: {str(e)}")

    if not search_keyword or "sorry" in search_keyword.lower() or "not identify" in search_keyword.lower():
        raise HTTPException(status_code=404, detail="I couldn't identify a clear product in this image. Please try a different photo.")

    found_products = await search_products_in_db(db, keyword=search_keyword)
    
    if not found_products:
         raise HTTPException(status_code=404, detail=f"I identified this as '{search_keyword}', but couldn't find any matching products in our database.")

    return found_products
