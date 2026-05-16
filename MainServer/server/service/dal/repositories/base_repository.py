from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, TypeVar, Generic
from sqlalchemy import select, update, delete
from uuid import UUID
from abc import ABC


class AbstractModel(ABC):
    """
    Абстрактный базовый класс для типизации.
    Не используется в наследовании моделей напрямую (ORM не требует этого)
    """
    id: UUID

T = TypeVar("T", bound=AbstractModel)

class BaseRepository(Generic[T]):
    model: type[T]

    @classmethod
    async def find_one_or_none(cls, db: AsyncSession, **filters) -> Optional[T]:
        result = await db.execute(select(cls.model).filter_by(**filters))
        return result.scalar_one_or_none()

    @classmethod
    async def find_all(cls, db: AsyncSession, **filters) -> list[T]:
        result = await db.execute(select(cls.model).filter_by(**filters))
        return list(result.scalars().all())

    @classmethod
    def create(cls, db: AsyncSession, **values) -> T:
        instance = cls.model(**values)
        db.add(instance)
        return instance

    @classmethod
    async def update_by_id(cls, db: AsyncSession, id_: UUID, **values) -> bool:
        result = await db.execute(
            update(cls.model).where(cls.model.id == id_).values(**values)
        )
        return result.rowcount > 0

    @classmethod
    async def delete_by_id(cls, db: AsyncSession, id_: UUID) -> bool:
        result = await db.execute(delete(cls.model).where(cls.model.id == id_))
        return result.rowcount > 0
