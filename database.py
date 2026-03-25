from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, Text, select

import config

DATABASE_URL = (
    f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}"
    f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_timeout=config.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

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
    title        = Column(String)
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
    price               = Column(Numeric(10, 2), nullable=True)
    original_price      = Column(Numeric(10, 2), nullable=True)
    discount_percentage = Column(Numeric(10, 2), nullable=True)
    external_url        = Column(String)
    is_available        = Column(Boolean, default=True)
    condition           = Column(String)
    seller_username     = Column(String)
    currency            = Column(String)
    quantity            = Column(Integer, default=0)
    free_shipping       = Column(Boolean, default=False)
    shipping_cost       = Column(Numeric(10, 2), nullable=True)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class User(Base):
    __tablename__ = "account_user"
    id    = Column(Integer, primary_key=True)
    name  = Column(String)
    email = Column(String)


async def get_user_profile(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()