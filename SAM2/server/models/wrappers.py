import numpy as np
from server.config import settings

from server.models.groundingdino_model import (
    GroundingDinoDetectionModel, 
    GroundingDinoSahiDetectionModel,
)
from server.models.sam_model import GroundedSAM2Model


def reform_data(result: dict):
    result['xyxy'] = [[int(x) for x in box] for box in result['xyxy']]
    result['confidence'] = [round(float(c), 3) for c in result['confidence']]
    if 'mask_score' in result:
        result['mask_score'] = [[round(float(c[0]), 3) for c in result['mask_score']]]
    return result


class GroundingDinoWrapper:
    """Обёртка для GroundingDinoDetectionModel с ленивой загрузкой."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._model = None
        self._initialized = True
    
    def load(self):
        """Загружает модель (вызывать при старте приложения)."""
        if self._model is None:
            print(f"Загрузка GroundingDINO на {settings.DEVICE}...")
            self._model = GroundingDinoDetectionModel(
                config_path = settings.GROUNDING_DINO_CONFIG,
                weights_path=settings.GROUNDING_DINO_WEIGHTS,
                box_threshold=settings.BOX_THRESHOLD,
                text_threshold=settings.TEXT_THRESHOLD,
                nms_threshold=settings.NMS_THRESHOLD,
                device=settings.DEVICE,
            )
            print("GroundingDINO загружен")
    
    def get_model(self):
        return self._model

    def detect(
        self,
        image: np.ndarray,
        texts: list[str],
    ) -> dict:
        """Выполняет детекцию, возвращает bounding boxes."""
        if self._model is None:
            self.load()

        result = self._model.detect_objects(
            image=image,
            texts=texts,
        )
        return reform_data(result)
    
    def cleanup(self):
        """Освобождает ресурсы модели."""
        if self._model is not None:
            del self._model
            self._model = None
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


class GroundingDinoSahiWrapper:
    """Обёртка для GroundingDinoSahiDetectionModel."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._base_wrapper = GroundingDinoWrapper()
        self._sahi_model = None
        self._initialized = True
    
    def load(self):
        """Загружает SAHI обёртку."""
        if self._sahi_model is None:
            self._base_wrapper.load()  # Убедимся, что базовая модель загружена
            print(f"Инициализация SAHI обёртки (slice={settings.SAHI_SLICE_WH})...")
            self._sahi_model = GroundingDinoSahiDetectionModel(
                base_model=self._base_wrapper._model,
                slice_wh=settings.SAHI_SLICE_WH,
                overlap_ratio=settings.SAHI_OVERLAP,
            )
            print("SAHI обёртка готова")
    
    def detect(
        self,
        image: np.ndarray,
        texts: list[str],
    ) -> dict:
        """Выполняет детекцию с SAHI slicing."""
        if self._sahi_model is None:
            self.load()
        
        result = self._sahi_model.detect_objects(
            image=image,
            texts=texts,
        )
        return reform_data(result)
    
    def cleanup(self):
        """Освобождает ресурсы."""
        if self._sahi_model is not None:
            self._sahi_model.cleanup()
            self._sahi_model = None


class GroundedSAM2Wrapper:
    """Обёртка для GroundedSAM2Model с поддержкой разных grounding моделей."""
    
    _instances: dict[str, 'GroundedSAM2Wrapper'] = {}
    
    def __new__(cls, grounding_variant: str = "standard"):
        """Factory method: создаёт экземпляр для нужного варианта grounding."""
        if grounding_variant not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            instance._grounding_variant = grounding_variant
            cls._instances[grounding_variant] = instance
        return cls._instances[grounding_variant]
    
    def __init__(self, grounding_variant: str = "standard"):
        if self._initialized:
            return
        self._model = None
        self._grounding_variant = grounding_variant
        self._initialized = True
    
    def load(self):
        """Загружает GroundedSAM2 с нужной grounding моделью."""
        if self._model is None:
            print(f"Загрузка GroundedSAM2 с {self._grounding_variant} grounding...")
            
            # Выбираем grounding модель
            if self._grounding_variant == "standard":
                grounding_model = self._load_single() if settings.SHARE_GROUNDING_DINO_MODEL else self._load_double()
            else:  # sahi
                if "standard" not in self._instances:
                    raise RuntimeError(
                        "GroundedSAM2Wrapper('standard') должен быть инициализирован первым!"
                    )
                standard_wrapper = self._instances["standard"]
                grounding_model = standard_wrapper._model.get_gd_model()
                if grounding_model is None:
                    raise RuntimeError("Grounding модель в standard экземпляре не загружена!")
                grounding_model = GroundingDinoSahiDetectionModel(
                    base_model=grounding_model,
                    slice_wh=settings.SAHI_SLICE_WH,
                    overlap_ratio=settings.SAHI_OVERLAP,
                )

            self._model = GroundedSAM2Model(
                sam2_model_config=settings.SAM2_CONFIG,
                sam2_checkpoint=settings.SAM2_CHECKPOINT,
                grounding_model=grounding_model,
                device=settings.DEVICE,
                use_bfloat16=settings.USE_BFLOAT16,
                multimask_output=False,
            )
            print(f"GroundedSAM2 ({self._grounding_variant}) загружен")

    def _load_single(self):
        return GroundingDinoWrapper().get_model()

    def _load_double(self):
        return GroundingDinoDetectionModel(
            config_path = settings.GROUNDING_DINO_CONFIG,
            weights_path=settings.GROUNDING_DINO_WEIGHTS,
            box_threshold=settings.BOX_THRESHOLD,
            text_threshold=settings.TEXT_THRESHOLD,
            nms_threshold=settings.NMS_THRESHOLD,
            device=settings.DEVICE,
        )
        
    def segment(
        self,
        image: np.ndarray,
        texts: list[str],
    ) -> dict:
        """Выполняет сегментацию."""
        if self._model is None:
            self.load()
        
        result = self._model.segment(
            image=image,
            texts=texts,
            return_format='dict',
        )
        return reform_data(result)
    
    def cleanup(self):
        """Освобождает ресурсы."""
        if self._model is not None:
            self._model.cleanup()
            self._model = None
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
