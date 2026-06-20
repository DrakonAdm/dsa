import asyncio
import httpx
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set, List
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

from server.service.dal.repositories import CacheObjectClassesRepository, ClassTypeRepository, TaskStatus, AnalysisTaskRepository
from server.service.application.annotation_service import AnnotationAnalyzeService
from server.core.dependencies import WebSocketManager, HandleMaskService
from server.service.transport.base_transport import CallbackPayload
from server.core.config import settings
from server.core.security import generate_callback_token, verify_callback_token

logger = logging.getLogger(__name__)


class TaskAnalyzeManager:
    """
    Управление очередями задач анализа.
    
    Ключевые принципы:
    - Одна очередь на уникальное имя модели (name), а не на variant
    - Callback освобождает слот → сразу запускает следующую задачу
    - Fernet-токены для защиты callback-запросов
    """
    
    def __init__(
        self,
        db_session_factory,
        http_client: httpx.AsyncClient,
        ws_manager: WebSocketManager,
        max_queue_size: int = settings.ANALYZE.MAX_QUEUE_SIZE,
        max_retries: int = settings.ANALYZE.MAX_RETRIES,
        base_backoff_sec: float = 5.0,
    ):
        self.db_factory = db_session_factory
        self.http_client = http_client
        self.ws_manager = ws_manager
        self.max_retries = max_retries
        self.base_backoff = base_backoff_sec
        self._max_queue_size = max_queue_size
        
        # Очереди по имени модели: name → Queue[UUID]
        self._queues: Dict[str, asyncio.Queue] = {}
        self._queue_locks: Dict[str, asyncio.Lock] = {}
        
        # какие модели сейчас заняты
        self._busy_models: Set[str] = set()
        self._slot_lock = asyncio.Lock()
        
        # какая задача сейчас обрабатывается на модели
        self._processing_tasks: Dict[str, UUID] = {}
        self._processing_lock = asyncio.Lock()
        
        # имя модели → set конфигураций (для быстрого доступа к endpoint)
        self._model_name_to_configs: Dict[str, Set[int]] = {}
        
        self._shutdown_event = asyncio.Event()

    async def initialize_from_repository(self, db: AsyncSession) -> None:
        """
        Инициализирует очереди и маппинги, используя кэш из CacheObjectClassesRepository.
        Вызывать при старте и после инвалидации кэша.
        """
        # Получаем сгруппированные конфиги из единого кэша
        configs_by_name = await CacheObjectClassesRepository.get_model_configs_by_name(db)
        
        # Обновляем внутренние структуры
        async with self._slot_lock:  # Блокируем на время перестройки
            # Создаём/обновляем очереди
            for name, configs in configs_by_name.items():
                if name not in self._queues:
                    self._queues[name] = asyncio.Queue(maxsize=self._max_queue_size)
                    self._queue_locks[name] = asyncio.Lock()
                    logger.info(f"Initialized queue for model: {name}")
                
                # Обновляем маппинг name → config_ids
                self._model_name_to_configs[name] = {cfg.id for cfg in configs}
            
            # Удаляем очереди для деактивированных/удалённых моделей
            active_names = set(configs_by_name.keys())
            stale_names = set(self._queues.keys()) - active_names
            for name in stale_names:
                self._queues.pop(name, None)
                self._queue_locks.pop(name, None)
                self._model_name_to_configs.pop(name, None)
                logger.info(f"Removed queue for deactivated model: {name}")
        
        logger.info(f"TaskManager initialized: {len(self._queues)} queues")
    
    async def enqueue_task(
        self,
        image_id: UUID,
        model_config_id: int,
        class_type_ids: List[UUID],
        ws_session_id: Optional[str] = None,
    ) -> UUID:
        """
        Создаёт задачу в БД и добавляет в очередь модели.
        Принимает model_config_id, имя модели определяется из кэша.

        :param class_type_ids: Список UUID классов из таблицы class_types
        """
        async with self.db_factory() as session:
            # Находим имя модели по config_id (через кэш)
            model_name = await self._get_model_name_by_config_id(model_config_id, session)
            if not model_name:
                # Кэш устарел? Пробуем обновить
                CacheObjectClassesRepository.invalidate_cache()
                await CacheObjectClassesRepository._ensure_cache_loaded(session)
                model_name = await self._get_model_name_by_config_id(model_config_id, session)
            
            if not model_name:
                raise ValueError(f"Model config {model_config_id} not found or inactive")
            
            # Проверяем, что очередь для этой модели существует
            if model_name not in self._queues:
                # Динамически добавленная модель — перестраиваем очереди
                await self.initialize_from_repository(session)
            
            queue = self._queues.get(model_name)
            if not queue:
                raise ValueError(f"Queue not available for model: {model_name}")
            
            # Генерируем task_id и токен
            task_id = uuid4()
            
            # Создаём запись в БД 
            await AnalysisTaskRepository.create_with_token(
                db=session,
                task_id=task_id,
                image_id=image_id,
                model_config_id=model_config_id,
                class_type_ids=class_type_ids,
                ws_session_id=ws_session_id,
            )
            await session.commit()
            
            # Добавляем task_id в очередь
            if queue.full():
                await self._update_task_status(task_id, TaskStatus.failed, "Queue full")
                raise ValueError(f"Queue for model '{model_name}' is full")
            
            await queue.put(task_id)
            logger.info(f"Enqueued task {task_id} -> model '{model_name}' with {len(class_type_ids or [])} classes")
            
            # Пытаемся сразу запустить обработку
            await self._try_dispatch_next(model_name)
            
            return task_id

    async def _try_dispatch_next(self, model_name: str):
        """Пытается взять следующую задачу из очереди и отправить на обработку."""
        queue = self._queues.get(model_name)
        if not queue or queue.empty():
            return
        
        async with self._slot_lock:
            if model_name in self._busy_models:
                return  # Занята
            
            async with self._queue_locks[model_name]:
                if queue.empty():
                    return
                task_id = await queue.get()
                self._busy_models.add(model_name)
        
        asyncio.create_task(
            self._process_task(task_id, model_name),
            name=f"process_{model_name}_{task_id}"
        )

    async def _process_task(self, task_id: UUID, model_name: str):
        """
        Загружает данные из БД и отправляет задачу на микросервис.
        
        Логика при 503:
        - Не освобождаем слот сразу
        - Повторяем запрос каждые 3 сек в течение 60 сек
        - Если всё ещё 503 после таймаута → освобождаем слот и вызываем error handler
        """
        try:
            # Фиксируем задачу в обработке (слот уже занят в _try_dispatch_next)
            async with self._processing_lock:
                self._processing_tasks[model_name] = task_id
            
            # Загружаем данные задачи из БД
            async with self.db_factory() as session:
                task = await AnalysisTaskRepository.find_by_id_with_image(session, task_id)
                if not task:
                    raise RuntimeError(f"Task {task_id} not found")
                
                if task.status == TaskStatus.cancelled:
                    logger.info(f"Task {task_id} cancelled, skipping")
                    raise RuntimeError(f"Task {task_id} cancelled, skipping")
                
                image_path = task.image.file_path
                model_config_id = task.model_config_id
                class_type_ids = task.class_type_ids or []
            
            texts = []
            if class_type_ids:
                async with self.db_factory() as session:
                    texts = await ClassTypeRepository.get_names_eng_by_ids(session, class_type_ids)
                
                if not texts:
                    logger.error(f"Task {task_id}: no valid class names found for ids {class_type_ids}")
                    raise RuntimeError(f"Endpoint not found for list classes UUID")
                    
            # Получаем endpoint из кэша
            endpoint_url = await self._get_endpoint_url(model_config_id)
            if not endpoint_url:
                raise RuntimeError(f"Endpoint not found for config {model_config_id}")
            
            callback_token = generate_callback_token(str(task_id))
            payload = {
                "image_path": image_path,
                "texts": texts,
                "callback_url": settings.ANALYZE.CALLBACK_BASE_URL,
                "output_suffix": None,
                "task_id": callback_token,
            }
            
            timeout = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=5.0)
            
            # 60 сек максимум, интервал 3 сек
            success = False
            start_time = asyncio.get_event_loop().time()
            max_wait_seconds = 60.0
            retry_interval = 3.0
            
            while asyncio.get_event_loop().time() - start_time < max_wait_seconds:
                try:
                    response = await self.http_client.post(
                        endpoint_url,
                        json=payload,
                        timeout=timeout,
                    )
                    
                    if response.status_code == 200:
                        success = True
                        logger.info(f"Task {task_id} successfully dispatched to '{model_name}'")
                        break  # Успех — выходим из цикла
                        
                    elif response.status_code == 503:
                        # Модель всё ещё занята — ждём и повторяем
                        logger.debug(f"Model '{model_name}' busy for task {task_id}, retrying in {retry_interval}s")
                        await asyncio.sleep(retry_interval)
                        continue
                        
                    else:
                        # Неожиданный статус — не повторяем, сразу ошибка
                        raise RuntimeError(f"Unexpected status {response.status_code}")
                        
                except httpx.ConnectError as e:
                    # Сетевая ошибка — можно повторить, но с осторожностью
                    logger.warning(f"Connection error for task {task_id}: {e}, retrying...")
                    await asyncio.sleep(retry_interval)
                    continue
            
            # Обработка результата цикла
            if success:
                # Успешная отправка — обновляем статус в БД
                await self._update_task_status(task_id, TaskStatus.processing)
                # Слот освободится в callback!
                
            else:
                # Таймаут исчерпан или критическая ошибка
                # Освобождаем слот и вызываем error handler
                await self._handle_dispatch_error(
                    task_id, 
                    model_name, 
                    error="Model busy after 60s retry timeout"
                )
                # Не делаем ничего больше — _handle_dispatch_error уже освободил слот
                
        except Exception as e:
            logger.error(f"Failed to process task {task_id}: {e}", exc_info=True)
            await self._handle_dispatch_error(task_id, model_name, e)

    async def _get_endpoint_url(self, config_id: int) -> Optional[str]:
        """
        Получает endpoint_url из кэша Repository.
        Не дублирует кэш, использует существующий.
        """
        # Гарантируем, что кэш загружен
        async with self.db_factory() as session:
            await CacheObjectClassesRepository._ensure_cache_loaded(session)
        
        return CacheObjectClassesRepository.get_endpoint_by_config_id(config_id)
    
    async def _get_model_name_by_config_id(self, config_id: int, db: AsyncSession) -> Optional[str]:
        """
        Находит имя модели по config_id через кэш Repository.
        Используется при enqueue, если имя не передано явно.
        """
        configs = await CacheObjectClassesRepository.get_base_classes(db)
        for cfg in configs:
            if cfg.id == config_id and cfg.is_active:
                return cfg.name
        return None
    
    async def _handle_busy_response(self, task_id: UUID, model_name: str, payload: dict):
        """Обработка 503: возвращаем задачу в очередь с backoff."""
        async with self._slot_lock:
            self._busy_models.discard(model_name)
        async with self._processing_lock:
            self._processing_tasks.pop(model_name, None)
        
        delay = min(self.base_backoff, 30.0)
        logger.warning(f"Model '{model_name}' busy for task {task_id}. Retrying in {delay}s")
        
        await asyncio.sleep(delay)
        
        queue = self._queues.get(model_name)
        if queue and not queue.full():
            await queue.put(task_id)
            await self._try_dispatch_next(model_name)
        else:
            await self._update_task_status(task_id, TaskStatus.failed, "Queue full after retry")

    async def _handle_dispatch_error(self, task_id: UUID, model_name: str, error: Exception):
        """
        Обработка ошибок: освобождает слот, обновляет статус, уведомляет клиента.
        Вызывается ТОЛЬКО когда слот нужно освободить.
        """
        # Загружаем ws_session_id перед освобождением слота
        """Крайне неудачное решение, НО возможно останеться навсегда)"""
        async with self.db_factory() as session:
            ws_session_id, image_id = await AnalysisTaskRepository.get_ws_session_and_image_id(
                db=session,
                task_id=task_id,
            ) or (None, None)

        # Освобождаем слот модели (если ещё не освобождён)
        async with self._slot_lock:
            self._busy_models.discard(model_name)
        
        # Удаляем из маппинга обрабатываемых задач
        async with self._processing_lock:
            self._processing_tasks.pop(model_name, None)
        
        # Обновляем статус в БД
        await self._update_task_status(task_id, TaskStatus.failed, str(error))
        
        # Уведомляем клиента через WebSocket
        await self._notify_ws(
            task_id=task_id,
            image_id=image_id,
            event="failed",
            ws_session_id=ws_session_id,
            error=str(error),
        )
        
        logger.warning(f"Task {task_id} failed: {error}")

    async def handle_callback(
        self,
        payload: CallbackPayload,
    ) -> dict:
        """
        Обрабатывает callback от микросервиса.
        
        Порядок операций для минимальной задержки:
        1. Верификация токена → task_id
        2. Быстрая проверка in-memory: задача действительно обрабатывалась?
        3. Немедленное освобождение слота модели
        4. Запуск следующей задачи из очереди (без ожидания БД!)
        5. Асинхронное сохранение результата в БД (фоновая задача)
        """
        try:
            # Верификация токена
            task_id_str = verify_callback_token(payload.task_id)
            if not task_id_str:
                logger.warning(f"Invalid callback token: {payload.task_id[:20]}...")
                return
            
            task_id = UUID(task_id_str)
            
            #  была ли задача в обработке?
            model_name = None
            async with self._processing_lock:
                # Ищем модель, где эта задача считалась "в обработке"
                for name, processing_task_id in self._processing_tasks.items():
                    if processing_task_id == task_id:
                        model_name = name
                        # Удаляем из маппинга + освобождаем слот атомарно
                        del self._processing_tasks[name]
                        async with self._slot_lock:
                            self._busy_models.discard(name)
                        break
            
            if not model_name:
                # Задача не найдена в _processing_tasks:
                # - Уже обработана ранее (дубль callback)
                # - Токен валиден, но задача была отменена
                # - Ошибка в логике (баг)
                logger.warning(f"Callback for task {task_id} not found in processing map (possible duplicate or cancelled)")
                return 
            
            logger.info(f"Slot released for model '{model_name}' (task {task_id})")
            
            # Немедленно запускаем следующую задачу из очереди
            asyncio.create_task(
                self._try_dispatch_next(model_name),
                name=f"dispatch_next_{model_name}"
            )
            # Сохранение результата в БД — в фоне, не блокируя поток
            asyncio.create_task(
                self._persist_callback_result(task_id, payload),
                name=f"persist_result_{task_id}"
            )
            return
        except Exception as e:
            logger.error(f"Callback processing error: {type(e).__name__}: {e}", exc_info=True)
            return

    async def _persist_callback_result(
        self,
        task_id: UUID,
        payload: CallbackPayload,
    ):
        """Фоновая задача: сохраняет результат callback в БД."""
        try:
            async with self.db_factory() as session:
                task = await AnalysisTaskRepository.find_by_id_with_image(session, task_id)
                if not task:
                    logger.warning(f"Task {task_id} not found during callback persistence")
                    return
                
                # Идемпотентность
                if task.status in (TaskStatus.completed, TaskStatus.failed):
                    logger.debug(f"Task {task_id} already finalized")
                    return
                
                ws_session_id = task.ws_session_id
                image_id = task.image_id
                
                # Сохраняем аннотации если задача успешна и есть результат
                annotation_result = []
                mask_ids = []
                
                if payload.success and payload.result:
                    result_data = payload.result
                    is_segmentation = payload.is_segmentation
                    
                    handle_mask_service = HandleMaskService()
                    
                    if is_segmentation:
                        # аннотации + маски + полигоны
                        annotations, masks = await AnnotationAnalyzeService.save_segmentation_annotations(
                            db=session,
                            image_id=image_id,
                            result=result_data,
                            handle_mask_service=handle_mask_service,
                        )
                        annotation_result = [
                            {
                                "annotation_id": str(a.id), 
                                "type": a.type, 
                                "class_name": a.class_name, 
                                "data": a.data
                            } 
                            for a in annotations
                        ]
                        mask_ids = [str(m.id) for m in masks]
                        logger.info(f"Saved {len(annotations)} segmentation annotations + {len(masks)} masks")
                    else:
                        # только bounding boxes
                        annotations = await AnnotationAnalyzeService.save_detection_annotations(
                            db=session,
                            image_id=image_id,
                            result=result_data,
                        )
                        annotation_result = [
                            {
                                "annotation_id": str(a.id), 
                                "type": a.type, 
                                "class_name": a.class_name, 
                                "data": a.data
                            } 
                            for a in annotations
                        ]
                        logger.info(f"Saved {len(annotations)} detection annotations")
                
                # Завершаем задачу в БД
                success = await AnalysisTaskRepository.finalize_with_result(
                    db=session,
                    task_id=task_id,
                    success=payload.success,
                    error_message=payload.error if not payload.success else None,
                )
                
                if not success:
                    logger.warning(f"Task {task_id} not found or already finalized")
                    return
                
                await session.commit()
                
                # Уведомляем клиента — добавляем ID созданных сущностей
                notification_result = {}
                if annotation_result:
                    notification_result["annotations"] = annotation_result
                if mask_ids:
                    notification_result["mask_ids"] = mask_ids

                # Если словарь пустой — отправляем None (для обратной совместимости)
                result_to_send = notification_result if notification_result else None
                
                await self._notify_ws(
                    task_id=task_id,
                    image_id=image_id,
                    event="completed" if payload.success else "failed",
                    ws_session_id=ws_session_id,
                    result=result_to_send,
                    error=payload.error if not payload.success else None,
                )
                
                logger.info(f"Task {task_id} persisted")
                
        except Exception as e:
            logger.error(f"Failed to persist callback result for task {task_id}: {e}", exc_info=True)
        
    async def _update_task_status(self, task_id: UUID, status: TaskStatus, error: Optional[str] = None):
        async with self.db_factory() as session:
            await AnalysisTaskRepository.update_status(
                db=session,
                task_id=task_id,
                new_status=status,
                error_message=error,
            )
            await session.commit()

    async def _notify_ws(
        self,
        task_id: UUID,
        image_id: UUID,
        event: str,
        ws_session_id: Optional[str] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        """
        Отправляет уведомление клиенту.
        
        Приоритет:
        1. Если ws_session_id указан → отправляем ТОЛЬКО в эту сессию
        2. Если ws_session_id None → fallback на broadcast по image_id
        """
        async with self.db_factory() as session:
            status = await AnalysisTaskRepository.get_status_by_id(session, task_id)
            if not status:
                return
            
            message = {
                "type": "task_update",
                "task_id": str(task_id),
                "image_id": str(image_id),
                "event": event,
                "status": status.value,
                "result": result,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            # конкретная сессия или широковещательная рассылка
            if ws_session_id:
                await self.ws_manager.send_to_session(ws_session_id, message)
                logger.debug(f"Sent {event} notification to session {ws_session_id}")
            else:
                # если сессия не указана — шлём всем, кто смотрит это изображение
                await self.ws_manager.broadcast_to_image(str(image_id), message)
                logger.debug(f"Broadcast {event} notification to image {image_id}")
    
    async def shutdown(self):
        logger.info("Shutting down TaskManager...")
        self._shutdown_event.set()