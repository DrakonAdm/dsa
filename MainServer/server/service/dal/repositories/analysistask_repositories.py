from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload 
from typing import List, Optional
from uuid import UUID

from server.service.dal.repositories.base_repository import BaseRepository
from server.service.db.shemas.models import TaskStatus, AnalysisTask, Image

class AnalysisTaskRepository(BaseRepository[AnalysisTask]):
    """Репозиторий для работы с задачами анализа."""
    model = AnalysisTask

    @classmethod
    async def find_by_id_with_image(
        cls,
        db: AsyncSession,
        task_id: UUID,
    ) -> Optional[AnalysisTask]:
        """
        Загружает задачу вместе со связанным изображением.
        
        Используется в _process_task и _persist_callback_result.
        """
        stmt = (
            select(cls.model)
            .options(selectinload(AnalysisTask.image))
            .where(cls.model.id == task_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def find_queued_task_with_user_check(
        cls,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
    ) -> Optional[AnalysisTask]:
        """
        Находит задачу со статусом 'queued' и проверяет принадлежность пользователю.
        
        Используется для валидации перед отменой задачи.
        """
        stmt = (
            select(cls.model)
            .join(Image, AnalysisTask.image_id == Image.id)
            .where(
                cls.model.id == task_id,
                Image.user_id == user_id,
                cls.model.status == TaskStatus.queued,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def create_with_token(
        cls,
        db: AsyncSession,
        task_id: UUID,
        image_id: UUID,
        model_config_id: int,
        class_type_ids: List[UUID],
        ws_session_id: Optional[str] = None,
    ) -> AnalysisTask:
        """
        Создаёт новую задачу анализа с генерацией токена.
        
        :return: созданный экземпляр задачи (ещё не закоммиченный)
        """
        task = cls.model(
            id=task_id,
            image_id=image_id,
            model_config_id=model_config_id,
            class_type_ids=class_type_ids or [],
            status=TaskStatus.queued,
            ws_session_id=ws_session_id,
        )
        db.add(task)
        return task

    @classmethod
    async def cancel_if_queued(
        cls,
        db: AsyncSession,
        task_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Атомарно отменяет задачу, если она ещё в статусе 'queued'.
        
        :return: True если отмена успешна, False если задача уже обрабатывается
        """
        stmt = (
            update(cls.model)
            .where(
                cls.model.id == task_id,
                cls.model.status == TaskStatus.queued,
                cls.model.image_id.in_(
                    select(Image.id).where(Image.user_id == user_id)
                )
            )
            .values(
                status=TaskStatus.cancelled,
                updated_at=func.now()
            )
        )
        result = await db.execute(stmt)
        return result.rowcount > 0

    @classmethod
    async def update_status(
        cls,
        db: AsyncSession,
        task_id: UUID,
        new_status: TaskStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Обновляет статус задачи с опциональными полями.
        """
        values = {
            "status": new_status,
            "updated_at": func.now(),
        }
        if error_message is not None:
            values["error_message"] = error_message
        if new_status in (TaskStatus.completed, TaskStatus.failed):
            values["completed_at"] = func.now()
        
        stmt = update(cls.model).where(cls.model.id == task_id).values(**values)
        result = await db.execute(stmt)
        return result.rowcount > 0

    @classmethod
    async def get_ws_session_and_image_id(
        cls,
        db: AsyncSession,
        task_id: UUID,
    ) -> Optional[tuple[str, UUID]]:
        """
        Быстро получает ws_session_id и image_id для уведомления.
        
        Используется в error handler, когда не нужна полная задача.
        """
        stmt = select(cls.model.ws_session_id, cls.model.image_id).where(
            cls.model.id == task_id
        )
        result = await db.execute(stmt)
        row = result.first()
        return (row[0], row[1]) if row and row[1] else None

    @classmethod
    async def finalize_with_result(
        cls,
        db: AsyncSession,
        task_id: UUID,
        success: bool,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Завершает задачу: устанавливает статус completed/failed и сохраняет результат.
        
        :return: True если обновление успешно, False если задача не найдена
        """
        values = {
            "updated_at": func.now(),
            "completed_at": func.now(),
        }
        if success:
            values["status"] = TaskStatus.completed
        else:
            values["status"] = TaskStatus.failed
            if error_message is not None:
                values["error_message"] = error_message
        
        stmt = update(cls.model).where(cls.model.id == task_id).values(**values)
        result = await db.execute(stmt)
        return result.rowcount > 0
    
    @classmethod
    async def get_status_by_id(cls, db: AsyncSession, task_id: UUID) -> Optional[TaskStatus]:
        stmt = select(cls.model.status).where(cls.model.id == task_id)
        result = await db.execute(stmt)
        status_val = result.scalar_one_or_none()
        return TaskStatus(status_val) if status_val else None