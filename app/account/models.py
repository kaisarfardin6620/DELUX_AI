from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base

class User(Base):
    __tablename__ = "account_user"
    id    = Column(Integer, primary_key=True)
    name  = Column(String)
    email = Column(String)

async def get_user_profile(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
