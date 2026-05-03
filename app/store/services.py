from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.store.models import Platform, Product, ProductListing
from app.store.schemas import ProductCard
from app.media_api.services import build_image_url

async def search_products_in_db(
    db: AsyncSession,
    keyword: str,
    max_price: float = None,
    min_price: float = None,
    condition: str = None,
    free_shipping: bool = None,
) -> List[ProductCard]:
    query = (
        select(Product, ProductListing, Platform)
        .join(ProductListing, Product.id == ProductListing.product_id)
        .join(Platform, ProductListing.platform_id == Platform.id)
        .where(ProductListing.is_available == True)
        .where(ProductListing.quantity > 0)
    )

    if keyword:
        query = query.where(Product.title.ilike(f"%{keyword}%"))
    if max_price is not None:
        query = query.where(ProductListing.price <= max_price)
    if min_price is not None:
        query = query.where(ProductListing.price >= min_price)
    if condition:
        query = query.where(ProductListing.condition == condition.strip().upper())
    if free_shipping is True:
        query = query.where(ProductListing.free_shipping == True)

    query = query.order_by(ProductListing.price.asc()).limit(5)

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
