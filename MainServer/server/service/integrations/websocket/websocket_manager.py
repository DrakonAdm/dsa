import asyncio
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Управление WebSocket-подключениями.
    
    Поддерживает:
    - Точную отправку в сессию (по session_id)
    - Рассылку всем подписчикам изображения (по image_id)
    - Отслеживание активных подключений по пользователю
    """
    
    def __init__(self):
        # user_id → set of WebSocket (для управления подключениями пользователя)
        self._user_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        
        # session_id → {websocket, user_id, subscribed_images}
        self._sessions: Dict[str, dict] = {}
        
        # image_id → set of session_id (для broadcast по изображению)
        self._image_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        self._lock = asyncio.Lock()
    
    async def connect(
        self, 
        websocket: WebSocket, 
        user_id: str, 
        session_id: str,
        image_id: Optional[str] = None,
    ):
        """
        Регистрирует новое подключение.
        
        :param image_id: сразу подписать сессию на изображение
        """
        await websocket.accept()
        
        async with self._lock:
            # Сохраняем сессию
            self._sessions[session_id] = {
                "websocket": websocket,
                "user_id": user_id,
                "subscribed_images": set([image_id]) if image_id else set(),
            }
            
            # Добавляем в подключения пользователя
            self._user_connections[user_id].add(websocket)
            
            # Подписка на изображение (если указано)
            if image_id:
                self._image_subscriptions[image_id].add(session_id)
        
        logger.info(f"WebSocket connected: user={user_id}, session={session_id}, image={image_id}")
    
    async def disconnect(self, session_id: str):
        """
        Отключает сессию и очищает все подписки.
        """
        async with self._lock:
            session_data = self._sessions.pop(session_id, None)
            if not session_data:
                return
            
            websocket = session_data["websocket"]
            user_id = session_data["user_id"]
            subscribed_images = session_data["subscribed_images"]
            
            # Удаляем из подключений пользователя
            self._user_connections[user_id].discard(websocket)
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]
            
            # Отменяем подписки на изображения
            for image_id in subscribed_images:
                self._image_subscriptions[image_id].discard(session_id)
                if not self._image_subscriptions[image_id]:
                    del self._image_subscriptions[image_id]
        
        logger.info(f"WebSocket disconnected: session={session_id}")
    
    async def send_to_session(self, session_id: str, message: dict) -> bool:
        """
        Отправляет сообщение в конкретную сессию.
        
        :return: True если успешно, False если сессия не найдена или закрыта
        """
        async with self._lock:
            session_data = self._sessions.get(session_id)
            if not session_id:
                logger.debug(f"Session {session_id} not found for direct message")
                return False
            websocket = session_data["websocket"]
        
        try:
            await websocket.send_json(message)
            return True
        except (WebSocketDisconnect, RuntimeError) as e:
            if "closed" in str(e).lower() or isinstance(e, WebSocketDisconnect):
                # Сессия закрыта — асинхронно очищаем
                asyncio.create_task(self.disconnect(session_id), name=f"cleanup_{session_id}")
                logger.warning(f"Session {session_id} closed during send, cleaned up")
            else:
                logger.error(f"Error sending to session {session_id}: {e}")
            return False
    
    async def broadcast_to_image(self, image_id: str, message: dict, exclude_session: Optional[str] = None):
        """
        Рассылает сообщение всем сессиям, подписанным на изображение.
        
        :param exclude_session: исключить сессию из рассылки
        """
        async with self._lock:
            session_ids = list(self._image_subscriptions.get(image_id, []))
        
        for session_id in session_ids:
            if session_id == exclude_session:
                continue
            success = await self.send_to_session(session_id, message)
            if not success:
                logger.debug(f"Failed to broadcast to session {session_id} for image {image_id}")
    
    async def subscribe_to_image(self, session_id: str, image_id: str) -> bool:
        """
        Подписывает сессию на уведомления по изображению.
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False
            
            self._sessions[session_id]["subscribed_images"].add(image_id)
            self._image_subscriptions[image_id].add(session_id)
        
        logger.debug(f"Session {session_id} subscribed to image {image_id}")
        return True
    
    async def unsubscribe_from_image(self, session_id: str, image_id: str) -> bool:
        """
        Отменяет подписку сессии на изображение.
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False
            
            self._sessions[session_id]["subscribed_images"].discard(image_id)
            self._image_subscriptions[image_id].discard(session_id)
            
            if not self._image_subscriptions[image_id]:
                del self._image_subscriptions[image_id]
        
        logger.debug(f"Session {session_id} unsubscribed from image {image_id}")
        return True
    
    def get_active_sessions_count(self) -> int:
        """Возвращает количество активных сессий (для мониторинга)."""
        return len(self._sessions)
    
    def get_subscribers_count(self, image_id: str) -> int:
        """Возвращает количество подписчиков на изображение."""
        return len(self._image_subscriptions.get(image_id, set()))