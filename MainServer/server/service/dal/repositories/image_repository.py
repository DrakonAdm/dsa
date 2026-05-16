from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, or_
from typing import List, Optional
from uuid import UUID

from server.service.dal.repositories.base_repository import BaseRepository
from server.service.db.shemas.models import Image, ImageType, Project, project_user_table


class ImageRepository(BaseRepository[Image]):
    model = Image

    @classmethod
    async def find_by_project_with_annotations(cls, db: AsyncSession, project_id: UUID) -> List[Image]:
        """
        Загружает активные изображения проекта вместе с их аннотациями.
        Использует selectinload для асинхронной загрузки отношений.
        """
        stmt = (
            select(cls.model)
            .options(selectinload(cls.model.annotations))
            .where(
                cls.model.project_id == project_id,
                cls.model.type_subscriptions == ImageType.active
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    @classmethod
    async def find_by_ids_and_project(cls, db, project_id: UUID, image_ids: List[UUID]):
        from sqlalchemy import select
        stmt = select(cls.model).where(
            cls.model.project_id == project_id,
            cls.model.id.in_(image_ids),
            cls.model.type_subscriptions == ImageType.active
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    @classmethod
    async def find_active_by_id_with_project_access(
        cls,
        db: AsyncSession,
        image_id: UUID,
        user_id: UUID,
    ) -> Optional[Image]:
        """
        Находит активное изображение и проверяет доступ через project_user_table.
        (Создатель проекта также считается участником, так как записывается в таблицу при создании)
        """
        stmt = (
            select(cls.model)
            .join(Project, cls.model.project_id == Project.id)
            .join(project_user_table, Project.id == project_user_table.c.project_by_id)
            .where(
                cls.model.id == image_id,
                cls.model.type_subscriptions == ImageType.active,
                project_user_table.c.user_by_id == user_id
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @classmethod
    async def get_project_id_by_image_id(cls, db: AsyncSession, image_id: UUID) -> Optional[UUID]:
        """
        Возвращает project_id для указанного изображения.
        Если изображение не найдено, возвращает None.
        """
        stmt = select(cls.model.project_id).where(cls.model.id == image_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @classmethod
    async def reload_list_image_upload(
        cls, 
        db: AsyncSession, 
        created_images: list[UUID]
    ) -> list[Image]:
        """
        Загружает все аннотации для загруженного изображения
        """
        image_ids = [img_id for img_id in created_images] 
        refreshed_images = await db.execute(
            select(cls.model)
            .where(cls.model.id.in_(image_ids))
            .options(selectinload(cls.model.annotations))
        )
        created_images = refreshed_images.scalars().all()
        return created_images
