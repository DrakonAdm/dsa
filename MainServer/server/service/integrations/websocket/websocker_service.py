from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import logging

from server.core.dependencies import ( 
    WebSocketManager, 
    TaskAnalyzeManager
)
from server.service.dal.repositories import AnalysisTaskRepository, ImageRepository, ImageType

logger = logging.getLogger("Analyze WebSocketServie")


class WebSocketService:
    @staticmethod
    async def send_error(session_id: str, ws_manager: WebSocketManager, message: str):
        """Вспомогательная функция для отправки ошибки в сессию."""
        await ws_manager.send_to_session(session_id, {
            "type": "error",
            "message": message
        })

    @staticmethod
    async def handle_start_analysis(
        session_id: str,
        data: dict,
        user_id: str,
        task_manager: TaskAnalyzeManager,
        ws_manager: WebSocketManager,
        db: AsyncSession,
    ):
        """
        Обработка команды start_analysis.
        
        Ожидаемый payload:
        {
            "cmd": "start_analysis",
            "image_id": "uuid",
            "class_type_ids": ["uuid1", "uuid2"],  # опционально, список UUID классов
            "model_config_id": 4  # ID модели из таблицы models
        }
        """
        # Валидация обязательных полей
        image_id = data.get("image_id")
        model_config_id = data.get("model_config_id")
        
        if not image_id or not model_config_id:
            await WebSocketService.send_error(session_id, ws_manager, "Missing image_id or model_config_id")
            return
        image_id = UUID(image_id) if isinstance(image_id, str) else image_id
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        
        # изображение существует, активно и принадлежит пользователю и у пользователя есть доступ к проекту, в который загружено изображений
        image = await ImageRepository.find_active_by_id_with_project_access(
            db=db,
            image_id=image_id,
            user_id=user_uuid,
        )
        if not image:
            logger.warning(
                f"Access denied: user={user_uuid} tried to access image={image_id}"
            )
            await WebSocketService.send_error(session_id, ws_manager, "Image not found or access denied")
            return
        
        # Преобразуем class_type_ids в список UUID
        class_type_ids_raw = data.get("class_type_ids", [])
        class_type_ids = []
        for cid in class_type_ids_raw:
            try:
                class_type_ids.append(UUID(cid) if isinstance(cid, str) else cid)
            except (ValueError, TypeError):
                logger.warning(f"Invalid class_type_id format: {cid}")
                continue
        
        try:
            # создаём задачу через TaskAnalyzeManager
            task_id = await task_manager.enqueue_task(
                image_id=UUID(image_id) if isinstance(image_id, str) else image_id,
                model_config_id=int(model_config_id),
                class_type_ids=class_type_ids,
                ws_session_id=session_id,  # привязываем задачу к сессии
            )
            
            # Отправляем подтверждение создания задачи
            await ws_manager.send_to_session(session_id, {
                "type": "task_created",
                "task_id": str(task_id),
                "status": "queued",
                "message": "Task queued for processing"
            })
            
            # Автоматически подписываем сессию на изображение для получения результата
            await ws_manager.subscribe_to_image(session_id, str(image_id))
            
            logger.info(f"Task {task_id} created for session {session_id}")
            
        except ValueError as e:
            # Ошибка валидации (модель не найдена, очередь полная и т.д.)
            await WebSocketService.send_error(session_id, ws_manager, str(e))
        except Exception as e:
            logger.error(f"Failed to create task for session {session_id}: {e}", exc_info=True)
            await WebSocketService.send_error(session_id, ws_manager, "Failed to create analysis task")

    @staticmethod
    async def handle_cancel_task(
        session_id: str,
        task_id: str,
        user_id: str,
        ws_manager: WebSocketManager,
        db: AsyncSession,
    ):
        """Обработка команды cancel_task через репозиторий."""
        try:
            task_uuid = UUID(task_id) if isinstance(task_id, str) else task_id
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            
            cancelled = await AnalysisTaskRepository.cancel_if_queued(
                db=db,
                task_id=task_uuid,
                user_id=user_uuid,
            )
            
            if not cancelled:
                await WebSocketService.send_error(session_id, ws_manager, "Task not found or already processing")
                return
            
            # Уведомляем клиента
            await ws_manager.send_to_session(session_id, {
                "type": "task_cancelled",
                "task_id": str(task_id),
                "message": "Task cancelled successfully"
            })
            
            logger.info(f"Task {task_id} cancelled by user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}", exc_info=True)
            await WebSocketService.send_error(session_id, ws_manager, "Failed to cancel task")