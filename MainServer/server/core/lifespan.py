from contextlib import asynccontextmanager
from sqlalchemy import select, text
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import asyncio
import logging
import httpx

from server.core.config import settings
from server.service.db.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from server.service.db.shemas.models import Base
from server.service.db.shemas.admin import add_event_listen
from server.core.internal_auth import internal_auth_service
from server.core.dependencies import get_database, get_db_session, TaskAnalyzeManager, WebSocketManager
from server.service.dal.repositories.cache_repository import ModelConfigRepository, CacheObjectClassesRepository


logger = logging.getLogger(__name__)

async def _init_database_classes(db: AsyncSession):
    """Инициализация справочников классов в БД при старте"""
    try:
        # Проверяем, есть ли уже записи
        result = await db.execute(select(ModelConfigRepository.model))
        if result.scalars().first():
            return  # Уже инициализировано
        
        # Создаём экземпляры из конфига
        instances = [
            ModelConfigRepository.model(
                name=item.name,
                type=item.type,
                endpoint_url=item.endpoint_url,
                is_active=item.is_active
            )
            for item in settings.MODEL_CONFIG_DEFAULT
        ]
        
        if instances:
            db.add_all(instances)
            await db.commit()
            
    except Exception as e:
        await db.rollback()
        raise  # Или return, если продолжить без справочника

async def wait_for_db(max_retries: int = 10, delay: float = 2.0):
    """Ожидание готовности базы данных с повторными попытками"""
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("Database connection successful")
                return True
        except Exception as e:
            logger.warning(f"Database not ready (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Failed to connect to database after all attempts")
                raise

async def add_root_service(app: FastAPI):
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,      # подключение к сервису
            read=30.0,       # ожидание ответа
            write=10.0,       # отправка payload
            pool=5.0          # ожидание свободного соединения из пула
        ),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.http_client = http_client
    app.state.ws_manager = WebSocketManager()
    
    # Создаём TaskManager
    app.state.task_manager = TaskAnalyzeManager(
        db_session_factory=get_db_session,
        http_client=app.state.http_client,
        ws_manager=app.state.ws_manager,
    )
    
    # Инициализируем очереди через Repository
    async with get_db_session() as db:
        await app.state.task_manager.initialize_from_repository(db)
    
    # Регистрируем колбэк для авто-обновления при инвалидации кэша
    def on_cache_invalidated():
        async def refresh():
            async with get_db_session() as db:
                await app.state.task_manager.initialize_from_repository(db)
        asyncio.create_task(refresh(), name="refresh_task_queues")
    
    CacheObjectClassesRepository.register_invalidation_callback(on_cache_invalidated)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Управление жизненным циклом приложения.
    Выполняется при старте и остановке сервера.
    """
    
    # Создание таблиц (если не существуют)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Инициализация моделей и ссылок на них
    async with get_database() as db:
        await _init_database_classes(db)
        await CacheObjectClassesRepository._ensure_cache_loaded(db)
        await internal_auth_service.refresh_from_cache(db)
    
    # Регистрация событий БД для инвалидации кэша
    add_event_listen()
    await add_root_service(app)

    yield

    # Корректное закрытие пула соединений
    await engine.dispose()