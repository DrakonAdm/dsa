import numpy as np
from server.config import settings
from sahi.predict import get_sliced_prediction

from server.models.yoloworld_model import YoloWorldDetectionModel
from server.models.yolo_sahi_model import YoloWorldSahiDetectionModel


def reform_text_classes(text: list[str]):
    classes = []
    for element in text:
        classes.append([element])
    return classes

class YoloWorldWrapper:
    """Обёртка для YoloWorldDetectionModel с ленивой загрузкой."""
    
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
            self._model = YoloWorldDetectionModel(
                config_path=settings.YoloWorld_CONFIG,
                weights_path=settings.YoloWorld_WEIGHTS,
                score_thr=settings.SCORE_THRESHOLD, 
                nms_thr=settings.NMS_THRESHOLD,
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

        texts = reform_text_classes(text=texts)
        result = self._model.detect_objects(
            frame=image,
            texts=texts,
        )
        return self.reform_data(result)
    
    @staticmethod
    def reform_data(result: dict):
        result['xyxy'] = [[int(x) for x in box] for box in result['xyxy']]
        result['confidence'] = [round(float(c), 3) for c in result['confidence']]
        return result

    def cleanup(self):
        """Освобождает ресурсы модели."""
        if self._model is not None:
            del self._model
            self._model = None
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


class YoloWorldSahiSahiWrapper:
    """Обёртка для YoloWorldSahiDetectionModel."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._base_wrapper = YoloWorldWrapper()
        self._sahi_model = None
        self._initialized = True
    
    def load(self):
        """Загружает SAHI обёртку."""
        if self._sahi_model is None:
            self._base_wrapper.load()  # Убедимся, что базовая модель загружена
            print(f"Инициализация SAHI обёртки (slice={settings.SAHI_SLICE_WH})...")
            self._sahi_model = YoloWorldSahiDetectionModel(
                base_model=self._base_wrapper._model,
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
        
        texts = reform_text_classes(text=texts)
        self._sahi_model.load_classes(texts=texts)
        slice_width, slice_height = settings.SAHI_SLICE_WH
        overlap_width_ratio, overlap_height_ratio = settings.SAHI_OVERLAP
        result = get_sliced_prediction(
            image,
            self._sahi_model,
            slice_height=slice_height,
            slice_width=slice_width,
            overlap_height_ratio=overlap_height_ratio,
            overlap_width_ratio=overlap_width_ratio,
            postprocess_match_threshold=0.3,
            verbose=True
        )
        """"
            result.object_prediction_list[0].bbox.(maxx, maxy, minx, miny)
            result.object_prediction_list[0].category.(id, name)
        """

        return self.sahi_to_custom_format(result=result)
    
    @staticmethod
    def sahi_to_custom_format(result):
        return {
            'xyxy': [
                [int(obj.bbox.minx), int(obj.bbox.miny), int(obj.bbox.maxx), int(obj.bbox.maxy)]
                for obj in result.object_prediction_list
            ],
            'class': [obj.category.name for obj in result.object_prediction_list],
            'confidence': [
                round(obj.score.value, 3) if hasattr(obj.score, 'value') else round(float(obj.score), 3)
                for obj in result.object_prediction_list
            ]
        }

    def cleanup(self):
        """Освобождает ресурсы."""
        if self._sahi_model is not None:
            self._sahi_model.cleanup()
            self._sahi_model = None
