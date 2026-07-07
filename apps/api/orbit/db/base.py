from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from orbit.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=(settings.env == "development"))
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
