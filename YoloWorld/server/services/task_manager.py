import asyncio
import uuid
import time
import logging
from enum import Enum
from typing import Callable, Optional, Any, Dict

from server.config import settings

logger = logging.getLogger(__name__)

class ModelVariant(Enum):
    """Варианты моделей."""
    YOLO_STANDARD = "yolo_standard"
    YOLO_SAHI = "yolo_sahi"

class SlotType(Enum):
    """Типы слотов исполнения."""
    SHARED = "shared"           # Один слот на всё


class TaskManager:
    """
    Простой менеджер задач с ограничением параллелизма.
    
    Логика:
    1. Если SHARE_GROUNDING_DINO_MODEL=True: 
       - Есть 1 общий слот. Детекция и сегментация конкурируют за него.
    2. Если SHARE_GROUNDING_DINO_MODEL=False:
       - Есть 2 слота: один для детекции, один для сегментации. Работают независимо.
    
    Если слот занят -> задача НЕ принимается (возврат False), без ожидания в очереди.
    """
    
    def __init__(self):
        # Словарь слотов: ключ -> {"lock": asyncio.Lock, "is_busy": bool}
        # Используем dict для удобного доступа по имени слота
        self._slots: Dict[str, Dict[str, Any]] = {}
        
        # Конфигурация "Одна задача на всё"
        self._slots[SlotType.SHARED.value] = {
            "lock": asyncio.Lock(),
            "is_busy": False
        }
        # Маппинг: любой вариант модели -> общий слот
        self._variant_to_slot = {v: SlotType.SHARED.value for v in ModelVariant}
        logger.info("TaskManager init: SHARED mode (1 slot for all)")

    def _get_slot_name(self, variant: ModelVariant) -> str:
        """Возвращает имя слота для данного типа модели."""
        return self._variant_to_slot[variant]
    
    async def acquire(self, variant: ModelVariant) -> bool:
        """
        Пытается заблокировать слот.
        Returns: True если успешно, False если занят.
        """
        slot_name = self._get_slot_name(variant)
        slot = self._slots[slot_name]
        async with slot["lock"]:
            if slot["is_busy"]:
                return False
            slot["is_busy"] = True
        return True
    
    async def release(self, variant: ModelVariant) -> None:
        """Освобождает слот (гарантированно, даже если уже свободен)."""
        slot_name = self._get_slot_name(variant)
        slot = self._slots[slot_name]
        async with slot["lock"]:
            slot["is_busy"] = False

    def is_available(self, variant: ModelVariant) -> bool:
        """
        Проверяет, свободен ли слот для задачи.
        Не блокирует, возвращает результат мгновенно.
        """
        slot_name = self._get_slot_name(variant)
        # в многопоточной среде нужна осторожность, но в asyncio это атомарно, если между проверкой и захватом нет yield.
        return not self._slots[slot_name]["is_busy"]

    def get_status(self) -> dict:
        """Возвращает статус слотов для мониторинга."""
        status = {}
        for name, data in self._slots.items():
            status[name] = {
                "busy": data["is_busy"],
                "available": not data["is_busy"]
            }
        return status
    
    async def shutdown(self, timeout: float = 30.0):
        """Корректная остановка с ожиданием завершения активных задач."""
        logger.info("TaskManager shutdown initiated...")
        
        # cобираем список занятых слотов
        busy_slots = [name for name, data in self._slots.items() if data["is_busy"]]
        
        if not busy_slots:
            logger.info("TaskManager shutdown complete (no active tasks)")
            return
        
        logger.info(f"Waiting for {len(busy_slots)} active task(s) to complete...")
        
        # ждём, пока слоты освободятся
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not any(self._slots[name]["is_busy"] for name in busy_slots):
                logger.info("All tasks completed, shutdown complete")
                return
            await asyncio.sleep(0.5)  # не блокируем цикл событий
        
        # таймаут истёк
        logger.warning(
            f"Shutdown timeout ({timeout}s) reached. "
            f"Active slots: {[n for n in busy_slots if self._slots[n]['is_busy']]}"
        )
