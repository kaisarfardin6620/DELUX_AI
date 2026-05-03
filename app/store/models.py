from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, Text
from app.core.database import Base

class Platform(Base):
    __tablename__ = "api_integration_platform"
    id   = Column(Integer, primary_key=True)
    name = Column(String)
    code = Column(String)

class Category(Base):
    __tablename__ = "api_integration_category"
    id        = Column(Integer, primary_key=True)
    name      = Column(String)
    slug      = Column(String)
    parent_id = Column(Integer, ForeignKey("api_integration_category.id"), nullable=True)

class Product(Base):
    __tablename__ = "api_integration_product"
    id           = Column(Integer, primary_key=True)
    title        = Column(String, index=True)
    description  = Column(Text)
    main_image   = Column(String)
    brand        = Column(String)
    model_number = Column(String)
    category_id  = Column(Integer, ForeignKey("api_integration_category.id"), nullable=True)

class ProductListing(Base):
    __tablename__ = "api_integration_productlisting"
    id                  = Column(Integer, primary_key=True)
    product_id          = Column(Integer, ForeignKey("api_integration_product.id"))
    platform_id         = Column(Integer, ForeignKey("api_integration_platform.id"))
    price               = Column(Numeric(10, 2), nullable=True, index=True)
    original_price      = Column(Numeric(10, 2), nullable=True)
    discount_percentage = Column(Numeric(10, 2), nullable=True)
    external_url        = Column(String)
    is_available        = Column(Boolean, default=True, index=True)
    condition           = Column(String, index=True)
    seller_username     = Column(String)
    currency            = Column(String)
    quantity            = Column(Integer, default=0)
    free_shipping       = Column(Boolean, default=False)
    shipping_cost       = Column(Numeric(10, 2), nullable=True)
