import torch
from sahi.model import DetectionModel
from sahi.prediction import ObjectPrediction
from torchvision.ops import nms
from typing import List

from server.config import settings
from server.models.yoloworld_model import YoloWorldDetectionModel

class YoloWorldSahiDetectionModel(DetectionModel):
    def __init__(
        self, 
        config_path: str = settings.YoloWorld_CONFIG, 
        weights_path: str = settings.YoloWorld_WEIGHTS,  
        score_thr=settings.SCORE_THRESHOLD, 
        nms_thr=settings.NMS_THRESHOLD, 
        device=settings.DEVICE,
        base_model: YoloWorldDetectionModel = None,
        **kwargs
    ):
        super().__init__(
            model_path=weights_path, 
            device=device, 
            **kwargs
        )
        if base_model:
            self.yolo_model = base_model
        else:
            self.yolo_model = YoloWorldDetectionModel(
                config_path=config_path,
                weights_path=weights_path,
                score_thr=score_thr,
                nms_thr=nms_thr,
                device=device,
            )

        self.texts = [[" "]]
        # Инициализация внутренних списков SAHI
        self._original_predictions = None
        self._object_prediction_list = []

    def load_model(self):
        """
        Переопределяем метод загрузки модели.
        Оставляем пустым, так как модель загружается в __init__ через ObjectDetector.
        Это предотвращает ошибку NotImplementedError.
        """
        pass

    def load_classes(
        self,
        texts: list[list[str]] = [["build"], ["car"]],
    ):
        self.texts = texts
        self.texts.append([" "])

    def perform_inference(self, numpy_image):
        """SAHI передает сюда numpy array (слайс)"""
        self._object_prediction_list = []
        
        if numpy_image is None or numpy_image.size == 0:
            self._original_predictions = None
            return

        try:
            pred_instances, data_info = self.yolo_model.prediction_instances(
                frame=numpy_image,
                texts=self.texts,
            )

            # NMS и фильтрация
            if len(pred_instances.scores) > 0:
                keep_idxs = nms(
                    pred_instances.bboxes, 
                    pred_instances.scores, 
                    iou_threshold=self.yolo_model.nms_thr
                )
                pred_instances = pred_instances[keep_idxs]
                pred_instances = pred_instances[pred_instances.scores.float() > self.yolo_model.score_thr]
                
                self._original_predictions = {
                    'bboxes': pred_instances.bboxes.cpu().numpy(),
                    'scores': pred_instances.scores.cpu().numpy(),
                    'labels': pred_instances.labels.cpu().numpy()
                }
            else:
                self._original_predictions = None
        except Exception as e:
            print(f"Error during inference: {e}")
            self._original_predictions = None

    def convert_original_predictions(
        self, full_shape=None, 
        category_mapping=None, 
        shift_amount=None, 
        **kwargs
    ):
        """
        Преобразование в формат SAHI.
        """
        self._object_prediction_list = []
        
        if shift_amount is None:
            shift_amount = [0, 0]
        
        if self._original_predictions is None or len(self._original_predictions['bboxes']) == 0:
            return self._object_prediction_list

        for i in range(len(self._original_predictions['bboxes'])):
            bbox = self._original_predictions['bboxes'][i]  # [x1, y1, x2, y2]
            score = self._original_predictions['scores'][i]
            label_id = int(self._original_predictions['labels'][i])
            
            category_name = self.texts[label_id][0] if label_id < len(self.texts) else f"class_{label_id}"
            
            object_prediction = ObjectPrediction(
                bbox=bbox.tolist(),
                category_name=category_name,
                category_id=label_id,
                score=score,
                shift_amount=shift_amount,
                full_shape=full_shape
            )
            self._object_prediction_list.append(object_prediction)
            
        return self._object_prediction_list

    @property
    def object_prediction_list(self) -> List[ObjectPrediction]:
        """Гарантируем корректный возврат списка предсказаний"""
        return self._object_prediction_list if self._object_prediction_list else []

    def unload_model(self):
        """Очистка памяти"""
        self.yolo_model.cleanup()
        torch.cuda.empty_cache()
