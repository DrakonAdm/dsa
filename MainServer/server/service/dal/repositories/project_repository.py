from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from typing import Union, List, Dict, Optional
from uuid import UUID

from server.service.dal.repositories.base_repository import BaseRepository
from server.service.db.shemas.models import Project, project_user_table, ClassTypeProject, Annotation, Image, Mask, AnnotationType


class ProjectRepository(BaseRepository[Project]):
    model = Project

    @staticmethod
    async def is_user_member(
        db: AsyncSession, 
        user_id: Union[UUID, str], 
        project_id: Union[UUID, str]
    ) -> bool:
        """
        Проверяет, является ли пользователь участником проекта.
        Использует select(1) для максимальной производительности.
        """
        stmt = select(1).where(
            project_user_table.c.project_by_id == project_id,
            project_user_table.c.user_by_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None
    
    @classmethod
    async def add_user_to_project(cls, db: AsyncSession, project_id: UUID, user_id: UUID) -> None:
        """Добавляет пользователя в таблицу связей проекта."""
        stmt = project_user_table.insert().values(
            project_by_id=project_id,
            user_by_id=user_id
        )
        await db.execute(stmt)
    
    @classmethod
    async def get_user_projects(cls, db: AsyncSession, user_id: UUID) -> List[Project]:
        stmt = (
            select(cls.model)
            .join(project_user_table, cls.model.id == project_user_table.c.project_by_id, isouter=True)
            .where(
                or_(
                    cls.model.created_by_id == user_id,
                    project_user_table.c.user_by_id == user_id
                )
            )
            .order_by(cls.model.created_at.desc())
            .distinct()
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


class ClassTypeRepository(BaseRepository[ClassTypeProject]):
    model = ClassTypeProject

    @staticmethod
    async def find_existing_by_names(
        db: AsyncSession,
        project_id: Union[UUID, str],
        class_names: List[str]
    ) -> List[ClassTypeProject]:
        """
        Находит существующие классы проекта по имени (на любом языке).
        :return: Список найденных записей ClassTypeProject
        """
        if not class_names:
            return []
            
        unique_names = list(set(class_names))
        stmt = select(ClassTypeProject).where(
            ClassTypeProject.project_id == project_id,
            or_(
                ClassTypeProject.name_ru.in_(unique_names),
                ClassTypeProject.name_eng.in_(unique_names)
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_many(
        db: AsyncSession,
        project_id: Union[UUID, str],
        class_types: List[Dict[str, str]]
    ) -> List[ClassTypeProject]:
        """
        Создаёт несколько записей классов проекта.
        :param class_types: Список словарей {'name_ru': str, 'name_eng': str}
        :return: Список созданных записей
        """
        if not class_types:
            return []
            
        from uuid import uuid4
        new_entries = [
            ClassTypeProject(
                id=uuid4(),
                project_id=project_id,
                name_ru=ct['name_ru'],
                name_eng=ct['name_eng']
            )
            for ct in class_types
        ]
        db.add_all(new_entries)
        await db.flush()
        return new_entries
    
    @staticmethod
    async def get_names_eng_by_ids(
        db: AsyncSession,
        class_type_ids: List[UUID]
    ) -> List[str]:
        """
        Возвращает список name_eng для заданных ID классов.
        Игнорирует несуществующие ID (не выбрасывает ошибку).
        """
        if not class_type_ids:
            return []
        
        stmt = select(ClassTypeProject.name_eng).where(
            ClassTypeProject.id.in_(class_type_ids)
        )
        result = await db.execute(stmt)
        # Фильтруем None и дубликаты, сохраняем порядок
        names = [name for name in result.scalars().all() if name]
        return names

class AnnotationRepository(BaseRepository[Annotation]):
    model = Annotation

    @classmethod
    async def async_create(cls, db: AsyncSession, **kwargs) -> Annotation:
        """Создает аннотацию и возвращает обновленный экземпляр."""
        instance = cls.model(**kwargs)
        db.add(instance)
        await db.flush()
        await db.refresh(instance)
        return instance

    @classmethod
    async def delete_by_project_and_class(cls, db: AsyncSession, project_id: UUID, class_name: str) -> int:
        """Удаляет аннотации класса только в пределах указанного проекта."""
        images_subquery = select(Image.id).where(Image.project_id == project_id)
        stmt = delete(cls.model).where(
            cls.model.image_id.in_(images_subquery),
            cls.model.class_name == class_name
        )
        result = await db.execute(stmt)
        return result.rowcount

    @staticmethod
    async def get_by_image_id(db: AsyncSession, image_id: UUID) -> List[Annotation]:
        stmt = select(Annotation).where(Annotation.image_id == image_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create_many(cls, db: AsyncSession, annotations: List[Annotation]) -> List[Annotation]:
        if not annotations:
            return []
        db.add_all(annotations)
        await db.flush()
        return annotations

    @classmethod
    async def delete_by_ids(cls, db: AsyncSession, ids: List[UUID]) -> int:
        if not ids:
            return 0
        stmt = delete(cls.model).where(cls.model.id.in_(ids))
        result = await db.execute(stmt)
        return result.rowcount

    @classmethod
    async def find_many_by_ids_and_image(cls, db: AsyncSession, ids: List[UUID], image_id: UUID) -> List[Annotation]:
        if not ids:
            return []
        stmt = select(cls.model).where(cls.model.id.in_(ids), cls.model.image_id == image_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def delete_by_ids_and_image(cls, db: AsyncSession, ids: List[UUID], image_id: UUID) -> int:
        if not ids:
            return 0
        stmt = delete(cls.model).where(cls.model.id.in_(ids), cls.model.image_id == image_id)
        result = await db.execute(stmt)
        return result.rowcount


class MaskRepository(BaseRepository[Mask]):
    model = Mask

    @classmethod
    async def delete_by_project_and_class(cls, db: AsyncSession, project_id: UUID, class_name: str) -> int:
        """Удаляет маски класса только в пределах указанного проекта."""
        images_subquery = select(Image.id).where(Image.project_id == project_id)
        stmt = delete(cls.model).where(
            cls.model.image_id.in_(images_subquery),
            cls.model.class_name == class_name
        )
        result = await db.execute(stmt)
        return result.rowcount
    
    @classmethod
    async def create_many(cls, db: AsyncSession, masks: List[Mask]) -> List[Mask]:
        """Создаёт несколько записей масок."""
        if not masks:
            return []
        db.add_all(masks)
        await db.flush()
        return masks

    @classmethod
    async def find_by_image_id(cls, db: AsyncSession, image_id: UUID) -> List[Mask]:
        """Находит все маски для изображения."""
        stmt = select(cls.model).where(cls.model.image_id == image_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def delete_by_image_id(cls, db: AsyncSession, image_id: UUID) -> int:
        """Удаляет все маски изображения."""
        stmt = delete(cls.model).where(cls.model.image_id == image_id)
        result = await db.execute(stmt)
        return result.rowcount