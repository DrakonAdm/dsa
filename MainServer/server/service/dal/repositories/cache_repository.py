from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, ClassVar, Dict, Set
from sqlalchemy import select
import asyncio
import logging

from server.service.dal.repositories.base_repository import BaseRepository
from server.service.db.shemas.models import ModelConfig
from server.service.transport.base_transport import ModelConfigInternal


logger = logging.getLogger(__name__)

class ModelConfigRepository(BaseRepository[ModelConfig]):
    model = ModelConfig

    @classmethod
    async def get_all_as_dicts(cls, db: AsyncSession) -> list[ModelConfigInternal]:
        stmt = select(cls.model.id, cls.model.name, cls.model.type, cls.model.endpoint_url, cls.model.is_active)
        result = await db.execute(stmt)
        return [
            ModelConfigInternal.model_validate(row._mapping) 
            for row in result
        ]


class CacheObjectClassesRepository:
    # Классовые переменные для кэша
    _base_classes_cache: ClassVar[Optional[list[ModelConfigInternal]]] = None
    _cache_lock: ClassVar = asyncio.Lock()  # для async-безопасности

    @classmethod
    async def _ensure_cache_loaded(cls, db: AsyncSession) -> None:
        """Ленивая инициализация кэша — один раз на всё приложение."""
        if cls._base_classes_cache is not None:
            return  # уже загружено

        # Защита от гонки: только один вызов может инициализировать
        async with cls._cache_lock:
            # Повторная проверка — после получения лока
            if cls._base_classes_cache is not None:
                return

            # Загружаем один раз
            cls._base_classes_cache = await ModelConfigRepository.get_all_as_dicts(db)

    @classmethod
    def invalidate_cache(cls) -> None:
        # Для sync-контекста (SQLAdmin) — можно без await, просто сбросить
        cls._base_classes_cache = None

    @classmethod
    async def get_base_classes(cls, db: AsyncSession) -> list[ModelConfigInternal]:
        await cls._ensure_cache_loaded(db=db)
        assert cls._base_classes_cache is not None, "Cache failed to load"
        return cls._base_classes_cache
    
    @classmethod
    async def get_dict_base_classes(cls, db: AsyncSession) -> Dict[str, str]:
        await cls._ensure_cache_loaded(db=db)
        assert cls._base_classes_cache is not None, "Cache failed to load"
        return {
            f"{row.name}_{row.type}": row.endpoint_url 
            for row in cls._base_classes_cache
        }
    
    @classmethod
    async def get_unique_model_names(cls, db: AsyncSession) -> Set[str]:
        """Возвращает уникальные имена активных моделей."""
        configs = await cls.get_base_classes(db)
        return {cfg.name for cfg in configs if cfg.is_active}
    
    @classmethod
    async def get_model_configs_by_name(cls, db: AsyncSession) -> Dict[str, list[ModelConfigInternal]]:
        """
        Группирует конфигурации по имени модели.
        Возвращает: {"Grounding Dino": [cfg1, cfg2], "Sam2": [cfg3, cfg4], ...}
        """
        configs = await cls.get_base_classes(db)
        result: Dict[str, list[ModelConfigInternal]] = {}
        for cfg in configs:
            if cfg.is_active:
                result.setdefault(cfg.name, []).append(cfg)
        return result
    
    @classmethod
    def get_endpoint_by_config_id(cls, config_id: int) -> Optional[str]:
        """
        Быстрый поиск endpoint_url по config_id из кэша.
        Вызывать только после ensure_cache_loaded().
        """
        if cls._base_classes_cache is None:
            return None
        for cfg in cls._base_classes_cache:
            if cfg.id == config_id and cfg.is_active:
                return cfg.endpoint_url
        return None
    
    _invalidation_callbacks: ClassVar[list[callable]] = []
    
    @classmethod
    def register_invalidation_callback(cls, callback: callable):
        """Регистрирует колбэк для вызова при инвалидации кэша."""
        cls._invalidation_callbacks.append(callback)
    
    @classmethod
    def invalidate_cache(cls) -> None:
        """Сбрасывает кэш и уведомляет зарегистрированные колбэки."""
        cls._base_classes_cache = None
        # Вызываем колбэки в фоне, чтобы не блокировать основной поток
        for cb in cls._invalidation_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Cache invalidation callback failed: {e}")
