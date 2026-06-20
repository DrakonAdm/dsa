import json
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from server.core.dependencies import (
    get_database, search_check_user, 
    WebSocketManager, get_websocket_manager, 
    TaskAnalyzeManager, get_task_manager, 
    )
from server.service.transport.base_transport import CallbackPayload, WSCommand
from server.service.integrations.websocket.websocker_service import WebSocketService

logger = logging.getLogger("AnalyzeRouter")


router = APIRouter(prefix='/api/analyze', tags=['Analyze'])


@router.websocket("/analysis")
async def analysis_websocket(
    websocket: WebSocket,
    token: str,  # токен передаётся в query params: /ws/analysis?token=xxx
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    task_manager: TaskAnalyzeManager = Depends(get_task_manager),
    db: AsyncSession = Depends(get_database),
):
    """
    WebSocket endpoint для управления задачами анализа.
    
    Поддерживаемые команды от клиента (JSON):
    
    1. {"cmd": "subscribe", "image_id": "uuid"}
       → подписка на уведомления по изображению
    
    2. {"cmd": "start_analysis", "image_id": "uuid", "class_type_ids": ["uuid1", "uuid2"], "model_config_id": 4}
       → запуск задачи анализа
    
    3. {"cmd": "cancel_task", "task_id": "uuid"}
       → отмена задачи (если ещё не началась обработка)
    
    4. {"cmd": "ping"}
       → проверка соединения, сервер отвечает {"type": "pong"}
    
    Ответы сервера (отправляются в сессию):
    
    - {"type": "task_created", "task_id": "uuid", "status": "queued"}
    - {"type": "task_update", "task_id": "uuid", "event": "processing|completed|failed", ...}
    - {"type": "error", "message": "..."}
    - {"type": "pong"}
    """
    
    # Аутентификация
    try:
        user = await search_check_user(token, logger, db)
        if not user:
            await websocket.close(code=4003, reason="Invalid or expired token")
            return
    except Exception as e:
        logger.error(f"Auth error in WebSocket: {e}")
        await websocket.close(code=4003, reason="Authentication failed")
        return
    
    # Генерация session_id и подключение
    session_id = str(uuid.uuid4())
    user_id = str(user.id)
    
    await ws_manager.connect(
        websocket=websocket,
        user_id=user_id,
        session_id=session_id,
    )
    logger.info(f"WebSocket connected: user={user_id}, session={session_id}")
    
    # цикл обработки сообщений
    try:
        while True:
            # Получаем сообщение от клиента
            raw_data = await websocket.receive_text()
            
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await ws_manager.send_to_session(session_id, {
                    "type": "error",
                    "message": "Invalid JSON format"
                })
                continue
            
            cmd = data.get("cmd")
            
            # Обработка команд
            if cmd == WSCommand.PING:
                await ws_manager.send_to_session(session_id, {"type": "pong"})
                
            elif cmd == WSCommand.SUBSCRIBE:
                image_id = data.get("image_id")
                if not image_id:
                    await WebSocketService.send_error(session_id, ws_manager, "Missing image_id")
                    continue
                success = await ws_manager.subscribe_to_image(session_id, str(image_id))
                if success:
                    await ws_manager.send_to_session(session_id, {
                        "type": "subscribed",
                        "image_id": image_id
                    })
                    
            elif cmd == WSCommand.UNSUBSCRIBE:
                image_id = data.get("image_id")
                if not image_id:
                    await WebSocketService.send_error(session_id, ws_manager, "Missing image_id")
                    continue
                await ws_manager.unsubscribe_from_image(session_id, str(image_id))
                await ws_manager.send_to_session(session_id, {
                    "type": "unsubscribed",
                    "image_id": image_id
                })
                    
            elif cmd == WSCommand.START_ANALYSIS:
                # Запуск задачи анализа
                await WebSocketService.handle_start_analysis(
                    session_id=session_id,
                    data=data,
                    user_id=user_id,
                    task_manager=task_manager,
                    ws_manager=ws_manager,
                    db=db,
                )
                    
            elif cmd == WSCommand.CANCEL_TASK:
                task_id = data.get("task_id")
                if not task_id:
                    await WebSocketService.send_error(session_id, ws_manager, "Missing task_id")
                    continue
                await WebSocketService.handle_cancel_task(
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    ws_manager=ws_manager,
                    db=db,
                )
                    
            else:
                await WebSocketService.send_error(session_id, ws_manager, f"Unknown command: {cmd}")
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
        await ws_manager.send_to_session(session_id, {
            "type": "error",
            "message": "Internal server error"
        })
    finally:
        # Гарантированная очистка
        await ws_manager.disconnect(session_id)
        logger.info(f"WebSocket cleanup complete: session={session_id}")


@router.post("/analysis")
async def analysis_callback(
    payload: CallbackPayload,
    background_tasks: BackgroundTasks,
    task_manager: TaskAnalyzeManager = Depends(get_task_manager),
):
    """
    Endpoint для приёма результатов от сервисов анализа.
    Возвращает 200 OK немедленно, обработка идёт в фоне.
    """
    background_tasks.add_task(
        task_manager.handle_callback,
        payload=payload,
    )
    return {"status": "accepted"}