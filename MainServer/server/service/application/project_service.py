from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import logging
from typing import List
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from server.service.dal.repositories import ProjectRepository, CacheObjectClassesRepository, ClassTypeRepository, UserRepository, AnnotationRepository, MaskRepository
from server.service.db.shemas.models import Project, User, ClassTypeProject
from server.core.dependencies import TranslationService
from server.service.transport import ProjectCreate, ClassTypeCreate, AddMemberRequest, ProjectsUserResponse
from server.service.transport.base_transport import ModelConfigBase

class ProjectService:
    @classmethod
    async def create_project(cls, db: AsyncSession, user: User, data: ProjectCreate, logger: logging.Logger) -> Project:
        project = ProjectRepository.create(db, name=data.name, created_by_id=user.id)
        await db.flush()
        await ProjectRepository.add_user_to_project(db, project.id, user.id)
        await db.commit()
        await db.refresh(project)
        return project
    
    @staticmethod
    async def get_user_projects(db: AsyncSession, user: User, logger: logging.Logger) -> ProjectsUserResponse:
        try:
            projects = await ProjectRepository.get_user_projects(db, user.id)
            logger.info(f"Successfully fetched {len(projects)} projects for user {user.id}")
            return ProjectsUserResponse(projects=projects)
        except Exception as e:
            logger.error(f"Error fetching projects for user {user.id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve projects")

    @classmethod
    async def delete_project(cls, db: AsyncSession, user: User, project_id: UUID, logger: logging.Logger) -> dict:
        project = await ProjectRepository.find_one_or_none(db, id=project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
        if project.created_by_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только создатель может удалить проект")
        
        await ProjectRepository.delete_by_id(db, id_=project_id)
        await db.commit()
        return {"detail": "Проект удален"}

    @classmethod
    async def get_available_models(cls, db: AsyncSession, logger: logging.Logger) -> list[ModelConfigBase]:
        internal_models = await CacheObjectClassesRepository.get_base_classes(db)
        return [ModelConfigBase.model_validate(m) for m in internal_models]

    @classmethod
    async def create_class_type(cls, db: AsyncSession, user: User, project_id: UUID, data: ClassTypeCreate, logger: logging.Logger) -> ClassTypeProject:
        project = await ProjectRepository.find_one_or_none(db, id=project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
        if project.created_by_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только создатель проекта может создавать классы")

        name_ru = data.name_ru
        name_eng = data.name_eng
        translator = TranslationService()
        loop = asyncio.get_event_loop()

        # Логика перевода: заполняем пропущенное поле через TranslationService
        if name_ru and not name_eng:
            translated = await loop.run_in_executor(None, translator.translate_list, [name_ru], 'ru', 'en')
            name_eng = translated[0] if translated else name_ru
        elif name_eng and not name_ru:
            translated = await loop.run_in_executor(None, translator.translate_list, [name_eng], 'en', 'ru')
            name_ru = translated[0] if translated else name_eng
        # Если оба указаны, используем их как есть

        class_type = ClassTypeRepository.create(
            db, 
            project_id=project_id, 
            name_ru=name_ru, 
            name_eng=name_eng
        )
        try:
            await db.commit()
            await db.refresh(class_type)
            return class_type
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Класс с таким названием уже существует в проекте")

    @classmethod
    async def delete_class_type(cls, db: AsyncSession, user: User, class_type_id: UUID, logger: logging.Logger) -> dict:
        class_type = await ClassTypeRepository.find_one_or_none(db, id=class_type_id)
        if not class_type:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Класс не найден")

        project = await ProjectRepository.find_one_or_none(db, id=class_type.project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
        if project.created_by_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только создатель проекта может удалять классы")

        # Логика удаления
        await AnnotationRepository.delete_by_project_and_class(db, project.id, class_type.name_eng)
        await MaskRepository.delete_by_project_and_class(db, project.id, class_type.name_eng)
        # Удаляем сам класс
        await ClassTypeRepository.delete_by_id(db, id_=class_type_id)

        await db.commit()
        return {"detail": "Класс и связанные аннотации/маски успешно удалены"}

    @classmethod
    async def get_class_types(cls, db: AsyncSession, user: User, project_id: UUID, logger: logging.Logger) -> List[ClassTypeProject]:
        if not await ProjectRepository.is_user_member(db, user.id, project_id):
            # Проверяем, создатель ли он (так как создатель автоматически считается участником. Если нет - проверка)
            project = await ProjectRepository.find_one_or_none(db, id=project_id)
            if not project or project.created_by_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")
                
        return await ClassTypeRepository.find_all(db, project_id=project_id)

    @classmethod
    async def add_member(cls, db: AsyncSession, user: User, project_id: UUID, data: AddMemberRequest, logger: logging.Logger) -> dict:
        if not data.email and not data.login:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите email или login пользователя")

        project = await ProjectRepository.find_one_or_none(db, id=project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
        if project.created_by_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только создатель может добавлять участников")

        # Поиск целевого пользователя
        target_user = await UserRepository.find_one_or_none(db, email=data.email) if data.email \
                      else await UserRepository.find_one_or_none(db, login=data.login)
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
        if target_user.id == user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя добавить себя")

        if await ProjectRepository.is_user_member(db, target_user.id, project_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже участник проекта")

        # SQLAlchemy автоматически вставит запись в project_user_table
        project.members.append(target_user)
        await db.commit()
        return {"detail": f"Пользователь {target_user.login} успешно добавлен"}