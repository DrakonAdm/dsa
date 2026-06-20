import httpx
import logging
import asyncio
from typing import Optional, Any
from server.config import settings

logger = logging.getLogger(__name__)

class CallbackService:
    """Сервис отправки результатов обработки на callback_url с повторными попытками."""
    
    def __init__(self):
        self.timeout = settings.CALLBACK_TIMEOUT_SEC
        self.max_retries = settings.CALLBACK_MAX_RETRIES
        self.retry_delay = settings.CALLBACK_RETRY_DELAY_SEC
    
    async def send(
        self,
        callback_url: str,
        payload: dict[str, Any],
        request_id: Optional[str] = None,
    ) -> bool:
        """
        Отправляет результат на callback_url с экспоненциальной задержкой при ошибках.
        
        Returns:
            True если отправка успешна, False если все попытки исчерпаны.
        """
        headers = {
            "X-Internal-Service-Token": settings.INTERNAL_SERVICE_TOKEN,
            "Content-Type": "application/json",
            "X-Request-ID": request_id or "",
        }
        
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        callback_url,
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    logger.info(f"Callback sent to {callback_url}, status: {response.status_code}")
                    return True
                    
            except httpx.TimeoutException:
                logger.warning(f"Callback timeout (attempt {attempt}/{self.max_retries})")
            except httpx.HTTPStatusError as e:
                logger.error(f"Callback HTTP error {e.response.status_code}: {e}")
                if 400 <= e.response.status_code < 500:
                    # Клиентская ошибка — повторять бессмысленно
                    return False
            except Exception as e:
                logger.error(f"Callback error (attempt {attempt}): {type(e).__name__}: {e}")
            
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)  # Экспоненциальная задержка
        
        logger.error(f"Failed to send callback after {self.max_retries} attempts")
        return False
