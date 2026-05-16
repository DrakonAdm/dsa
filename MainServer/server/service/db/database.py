import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from server.core.config import settings

# Создание асинхронного engine
engine = create_async_engine(
    settings.DB.url,
    echo=False,  # Включить для отладки SQL-запросов
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,   # Пересоздание соединений каждые 1 час
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

@asynccontextmanager
async def get_database() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для инъекции сессии БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Простая фабрика сессий для сервисного слоя.
    Не делает авто-коммит/роллбек — управление транзакциями на стороне вызывающего кода.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Переопределяем dependency для инъекции сессии"""
    async with get_database() as session:
        yield session

# Экспорт для удобства импорта
__all__ = ["engine", "get_database", "get_db_session", "get_db"]


"""
Миграции в бд:
alembic init alembic
alembic revision --autogenerate -m "Initial tables"
alembic upgrade head


Проверка миграций
alembic current
"""