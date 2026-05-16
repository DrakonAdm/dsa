import time
import logging
import asyncio
import numpy as np
from typing import Optional, Any, List, Dict
from collections import defaultdict

from server.config import settings
from server.services.task_manager import TaskManager, ModelVariant
from server.services.callback_service import CallbackService
from server.services.minio_service import MinIOService 
from server.models.wrappers import (
    GroundingDinoWrapper,
    GroundingDinoSahiWrapper,
    GroundedSAM2Wrapper,
)
from server.utils.image import load_image_from_bytes, encode_mask_to_png, serialize_for_json

logger = logging.getLogger(__name__)

class InferenceOrchestratorService:
    """
    Бизнес-логика сервиса детекции/сегментации.
    Координирует TaskManager, модели, MinIO и колбэки.
    """
    
    def __init__(self):
        self.task_manager = TaskManager()
        self.callback_service = CallbackService()
        self.minio = MinIOService()
        
        # Кэш моделей (ленивая загрузка)
        # Кэш моделей
        self._models: dict[ModelVariant, Any] = {}
        
        # Локи для потокобезопасной загрузки (защита от race condition)
        self._model_load_locks: dict[ModelVariant, asyncio.Lock] = {
            v: asyncio.Lock() for v in ModelVariant
        }

    def _get_model(self, variant: ModelVariant):
        """
        Возвращает экземпляр модели, загружая веса при первом вызове.
        Потокобезопасен: если два запроса придут одновременно, модель загрузится только один раз.
        """
        # модель уже загружена
        if variant in self._models and self._models[variant] is not None:
            return self._models[variant]
        
        # нужно загрузить (с блокировкой)
        # Используем синхронный lock, т.к. метод вызывается и из синхронного lifespan
        import threading
        if not hasattr(self, '_sync_load_locks'):
            self._sync_load_locks = {v: threading.Lock() for v in ModelVariant}
        
        with self._sync_load_locks[variant]:
            # Double-check после получения лока
            if variant in self._models and self._models[variant] is not None:
                return self._models[variant]
            
            print(f"Loading model: {variant.value}...")
            
            # Создаём и загружаем модель
            if variant == ModelVariant.DINO_STANDARD:
                model = GroundingDinoWrapper()
                model.load()
                self._models[variant] = model
                
            elif variant == ModelVariant.DINO_SAHI:
                model = GroundingDinoSahiWrapper()
                model.load()
                self._models[variant] = model
                
            elif variant in (ModelVariant.SAM2_STANDARD, ModelVariant.SAM2_SAHI):
                grounding = "standard" if variant == ModelVariant.SAM2_STANDARD else "sahi"
                model = GroundedSAM2Wrapper(grounding_variant=grounding)
                model.load()
                self._models[variant] = model
            
            print(f"Model {variant.value} loaded")
            
        return self._models[variant]

    async def unblock_model(self, variant: ModelVariant,):
        return await self.task_manager.release(variant=variant)
    
    async def acquire_model(self, variant: ModelVariant) -> bool:
        """Атомарная блокировка слота через TaskManager."""
        return await self.task_manager.acquire(variant)

    async def process_detection(
        self,
        image_path: str,
        texts: list[str],
        variant: ModelVariant,
        callback_url: Optional[str],
        output_suffix: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> tuple[str, bool, str]:
        """
        Запускает обработку изображения.
        
        Returns:
            (task_id, accepted, message):
            - accepted=True: задача принята, результат придёт на callback
            - accepted=False: очередь занята, клиенту нужно повторить запрос позже
        """
        start = time.time()
        error = None
        result = None

        is_segmentation = False
        try:
            result, is_segmentation = await self.image_analysis(
                image_path=image_path, 
                texts=texts, 
                variant=variant, 
                output_suffix=output_suffix
            )
            processing_time_ms = (time.time() - start) * 1000
            
        except Exception as e:
            error = e
            print(f"Error: {e}")
            processing_time_ms = (time.time() - start) * 1000
        
        finally:
        # Гарантированно освобождаем слот, даже при ошибке!
            try:
                await self.unblock_model(variant=variant)
                print(f"Slot released for {variant.value}")
            except Exception as e:
                print(f"Failed to release slot: {e}")
        
        payload = {
            "success": error is None,
            "error": str(error) if error else None,
            "processing_time_ms": processing_time_ms,
            "is_segmentation": is_segmentation,
            "model_type": variant.value,
            "task_id": task_id,
        }
        
        if result and error is None:
            payload["result"] = serialize_for_json(result)
        
        if callback_url:
            await self.callback_service.send(
                callback_url=callback_url,
                payload=payload,
            )
        print(f"Callback URL, result: {payload}")
    
    async def image_analysis(
        self,
        image_path: str,
        texts: list[str],
        variant: ModelVariant,
        output_suffix: Optional[str] = None,
    ):
        print(f"Starting inference for {image_path}")
        image_bytes = await asyncio.to_thread(
            self.minio.download_image, 
            image_path
        )
        if not image_bytes:
            raise RuntimeError(f"Failed to download {image_path}")
            
        image = await asyncio.to_thread(load_image_from_bytes, image_bytes)
        model = self._get_model(variant)
            
        if "sam2" in variant.value:
            h, w = image.shape[:2]
            result = await asyncio.to_thread(
                model.segment,
                image=image,
                texts=texts,
            )
            suffix = output_suffix or variant.value                    
            result['mask_path'] = await asyncio.to_thread(
                self._save_masks,
                masks=result['mask'],
                classes=result['class'],
                h=h, 
                w=w, 
                image_path=image_path,
                suffix=suffix
            )
            del result['mask']
            is_segmentation = True
        else:
            result = await asyncio.to_thread(
                model.detect,
                image=image,
                texts=texts,
            )
            is_segmentation = False
        
        return result, is_segmentation

    # def _save_masks(self, masks, classes, h, w, image_path, suffix):
    #     output_path = self.minio.generate_result_path(image_path, suffix)

    #     if masks.ndim == 3 and masks.shape[0] > 0:
    #         combined_mask = np.any(masks, axis=0)
    #     elif masks.ndim == 2:
    #         combined_mask = masks
    #     else:
    #         combined_mask = np.zeros((h, w), dtype=bool)
        
    #     # Кодируем маску в PNG (черно-белое изображение)
    #     mask_bytes = encode_mask_to_png(combined_mask)
    #     # Сохраняем в MinIO
    #     result_url = self.minio.upload_image(
    #         output_path, 
    #         mask_bytes, 
    #         content_type="image/png"
    #     )
    #     return result_url
    
    def _save_masks(
        self, 
        masks: np.ndarray,
        classes: List[str],
        h: int, w: int,      
        image_path: str,
        suffix: str, 
    ) -> List[Dict[str, str]]:
        """
        Сохраняет одну объединённую маску на каждый УНИКАЛЬНЫЙ класс.
        
        Returns:
            Список метаданных: [{"class": "car", "mask_path": "..."}, ...]
        """        
        if masks.ndim != 3 or masks.shape[0] != len(classes):
            raise ValueError(f"Invalid shapes: masks={masks.shape}, classes={len(classes)}")
        
        h, w = masks.shape[1:]
        class_masks: Dict[str, np.ndarray] = defaultdict(lambda: np.zeros((h, w), dtype=bool))
        
        # Группируем маски по классу и объединяем через logical_or
        for mask, cls in zip(masks, classes):
            if cls:  # пропускаем пустые классы
                class_masks[cls] = np.logical_or(class_masks[cls], mask)
        
        result_metadata = []
        for cls, combined_mask in class_masks.items():
            mask_bytes = encode_mask_to_png(combined_mask)
            safe_cls = cls.replace(" ", "_").lower()
            output_path = self.minio.generate_result_path(image_path, safe_cls + "_" + suffix)
            
            # Загружаем в MinIO
            mask_url = self.minio.upload_image(
                output_path,
                mask_bytes,
                content_type="image/png"
            )
            
            result_metadata.append({
                "class": cls,
                "mask_path": mask_url
            })
            print(f"Saved mask for class '{cls}': {mask_url}")
        
        return result_metadata

    def get_status(self):
        return self.task_manager.get_status()
    
    async def shutdown(self):
        """Корректная остановка сервиса."""
        await self.task_manager.shutdown()
        
        # Cleanup моделей
        for variant, model in self._models.items():
            try:
                print(f"Cleaning up {variant.value}...")
                if hasattr(model, "cleanup"):
                    model.cleanup()  # Освобождение VRAM, закрытие сессий и т.д.
            except Exception as e:
                print(f"Error cleaning up {variant.value}: {e}")
        
        self._models.clear()
        print("Models cleanup complete")
