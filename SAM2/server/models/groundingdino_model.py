import torch
import numpy as np
import cv2
import gc
import os
import shutil
from pathlib import Path
from typing import List, Dict, Union, Optional, Tuple
from torchvision.ops import nms
from torchvision.ops import box_convert
from PIL import Image

import supervision as sv
try:
    from groundingdino.models import build_model
    from groundingdino.util.slconfig import SLConfig
    from groundingdino.util.utils import clean_state_dict
    from groundingdino.util.inference import load_model, predict
    import groundingdino.datasets.transforms as T
except ImportError:
    raise ImportError(
        "GroundingDINO modules not found. "
        "Please ensure the GroundingDINO repository is cloned and added to sys.path."
    )


def caption_list(texts: list[str]):
    return " . ".join(texts) + " ."


def filter_oversized_objects(
        detections: Dict[str, np.ndarray], 
        image_shape: Tuple[int, int], 
        max_area_ratio: float = 0.7
    ) -> Dict[str, np.ndarray]:
        """
        Удаляет объекты, занимающие более max_area_ratio от площади изображения,
        НО только если существует хотя бы один объект меньшего размера.
        Если все объекты большие, они остаются нетронутыми.
        
        Args:
            detections: Словарь {'xyxy': np.array, 'class': List, 'confidence': np.array}
            image_shape: Кортеж (height, width)
            max_area_ratio: Порог площади (0.62 = 62% площади изображения)
            
        Returns:
            Отфильтрованный словарь detections
        """
        xyxy = detections['xyxy']
        if xyxy.shape[0] == 0:
            return detections
        
        h, w = image_shape
        image_area = h * w
        widths = xyxy[:, 2] - xyxy[:, 0]
        heights = xyxy[:, 3] - xyxy[:, 1]
        areas = widths * heights
        ratios = areas / image_area
        
        is_oversized = ratios > max_area_ratio
        has_normal_sized_objects = not np.all(is_oversized)
        if has_normal_sized_objects:
            keep_mask = ~is_oversized
        else:
            keep_mask = np.ones(len(ratios), dtype=bool)
        
        filtered_xyxy = xyxy[keep_mask]
        filtered_confidence = detections['confidence'][keep_mask]
        filtered_classes = [
            detections['class'][i] 
            for i in range(len(keep_mask)) 
            if keep_mask[i]
        ]
        
        return {
            'xyxy': filtered_xyxy,
            'class': filtered_classes,
            'confidence': filtered_confidence
        }


class GroundingDinoDetectionModel:
    """
    Класс для загрузки модели Grounding DINO и детекции объектов на полном изображении.
    """

    _image_transform = T.Compose(
        [
            T.RandomResize([800], max_size=1333),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    def __init__(
        self,
        config_path: str = "Grounded-SAM-2/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py",
        weights_path: str = "Grounded-SAM-2/gdino_checkpoints/groundingdino_swint_ogc.pth",
        bert_base_path: str = "Grounded-SAM-2/gdino_checkpoints/bert-base",
        box_threshold: float = 0.20,
        text_threshold: float = 0.15,
        nms_threshold: float = 0.22,
        device: str = 'cpu',
    ):
        self.config_path = config_path
        self.weights_path = weights_path
        self.bert_base_path = bert_base_path
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.nms_threshold = nms_threshold
        self.device = device
        self.model = None

        if self.bert_base_path:
            self._load_model_path()
        else:
            self._load_model()

    def _load_model(self):
        """Внутренний метод загрузки модели."""
        try:
            print(f"Loading Grounding DINO from {self.weights_path}...")
            self.model = load_model(
                model_config_path=self.config_path,
                model_checkpoint_path=self.weights_path,
                device=self.device
            )
            self.model.eval()
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Error loading model: {e}")
            raise e
    
    def _load_model_path(self):
        """Внутренний метод загрузки модели с поддержкой локального BERT."""
        try:
            print(f"Loading Grounding DINO from {self.weights_path}...")
                
            # Загружаем конфиг
            config = SLConfig.fromfile(self.config_path)
                
            if self.bert_base_path and os.path.exists(self.bert_base_path):
                print(f"Using local BERT model from: {self.bert_base_path}")
                config.text_encoder_type = self.bert_base_path
                
            # Строим модель с модифицированным конфигом
            self.model = build_model(config)
                
            # Загружаем веса
            checkpoint = torch.load(self.weights_path, map_location="cpu")
            load_res = self.model.load_state_dict(
                clean_state_dict(checkpoint["model"]), strict=False
            )
            print(f"Model load result: {load_res}")
                
            self.model.to(self.device)
            self.model.eval()
            print("Model loaded successfully.")
                
        except Exception as e:
            print(f"Error loading model: {e}")
            raise e
        
    def _transform_image(self, image: np.ndarray) -> torch.Tensor:
        """        
        Args:
            frame: Изображение в формате numpy array (H, W, C).
        Returns:
            torch.Tensor: Нормализованный тензор изображения.
        """
        if image is None or image.size == 0:
            raise ValueError("Input frame is empty or None")
        
        pil_image = Image.fromarray(image).convert("RGB")
        image_transformed, _ = self._image_transform(pil_image, None)
        return image_transformed

    def _run_inference(self, image_tensor: torch.Tensor, caption: str) -> tuple:
        """Запуск инференса модели."""
        with torch.no_grad():
            boxes, logits, phrases = predict(
                model=self.model,
                image=image_tensor,
                caption=caption,
                box_threshold=self.box_threshold,
                text_threshold=self.text_threshold,
                device=self.device,
            )
        return boxes, logits, phrases

    def _unique_nms(self, boxes_xyxy, logits, phrases):
        keep_indices = []
        unique_phrases = list(set(phrases))
        
        for phrase in unique_phrases:
            class_indices = [i for i, p in enumerate(phrases) if p == phrase]
            if len(class_indices) == 0:
                continue
                
            class_boxes = boxes_xyxy[class_indices]
            class_scores = logits[class_indices]
            nms_keep = nms(
                boxes=class_boxes,
                scores=class_scores,
                iou_threshold=self.nms_threshold
            )
            
            keep_indices.extend([class_indices[i] for i in nms_keep])

        return torch.tensor(keep_indices, dtype=torch.long)

    def update_threshold(
        self, 
        box_threshold: float = None, 
        text_threshold: float = None,
    ):
        if box_threshold:
            self.box_threshold = box_threshold
        if text_threshold:
            self.text_threshold = text_threshold
                
    def detect_objects(
        self, 
        image: np.ndarray, 
        texts: List[str] = ["build", "car"],
    ) -> Dict[str, np.ndarray]:
        """
        Основной метод детекции.
        Возвращает словарь в формате: {'xyxy': ..., 'class': ..., 'confidence': ...}
        """
        h, w, _ = image.shape
        caption = caption_list(texts)
        image = self._transform_image(image=image)
        boxes, logits, phrases = self._run_inference(image, caption)
        if len(boxes) == 0:
            return {
                'xyxy': np.empty((0, 4)),
                'class': [],
                'confidence': np.empty((0,))
            }
        
        boxes = boxes * torch.Tensor([w, h, w, h])
        xyxy = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xyxy")
        nms_indices = self._unique_nms(boxes_xyxy=xyxy, logits=logits, phrases=phrases)

        # Фильтрация результатов по индексам, оставленным после NMS
        xyxy_filtered = xyxy[nms_indices].detach().cpu().numpy()
        confidence_filtered = logits[nms_indices].detach().cpu().numpy()
        phrases_filtered = [phrases[i] for i in nms_indices]
        result = {
            'xyxy': xyxy_filtered,
            'class': phrases_filtered,
            'confidence': confidence_filtered
        }
        return filter_oversized_objects(
            detections=result, 
            image_shape=(h, w), 
            max_area_ratio=0.62
        )

    def visualization(
        self, 
        image: np.ndarray, 
        texts: List[str] = ["build", "car"]
    ) -> np.ndarray:
        """
        Визуализирует результат детекции на изображении.
        Возвращает аннотированное изображение (numpy array).
        """
        # Получаем детекции
        image_det = image.copy()
        detections_dict = self.detect_objects(image=image_det, texts=texts)

        phrases = detections_dict['class']
        unique_phrases = sorted(list(set(phrases)))
        class_map = {phrase: i for i, phrase in enumerate(unique_phrases)}
        class_ids = np.array([class_map[phrase] for phrase in phrases])
        
        detections = sv.Detections(xyxy=detections_dict['xyxy'], class_id=class_ids)
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator(text_position=sv.Position.CENTER)

        # Генерация лейблов
        labels = [
            f"{phrase} {logit:.2f}"
            for phrase, logit
            in zip(detections_dict["class"], detections_dict["confidence"])
        ]

        annotated_frame = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        annotated_image = box_annotator.annotate(scene=annotated_frame, detections=detections)
        # annotated_image = label_annotator.annotate(scene=annotated_image, detections=detections, labels=labels)

        return annotated_image

    def cleanup(self):
        """Освобождение ресурсов."""
        if self.model:
            self.model.to('cpu')
            del self.model
            self.model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def to_sam2_input(self, detections_dict: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Конвертирует результаты детекции в формат, совместимый с SAM2.
        
        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: 
                - input_boxes: bounding boxes в формате xyxy (numpy array)
                - confidences: массив уверенностей
                - class_names: список названий классов
        """
        xyxy = detections_dict['xyxy']
        confidence = detections_dict['confidence']
        class_names = detections_dict['class']
        
        # SAM2 ожидает boxes в формате xyxy как numpy array
        input_boxes = xyxy.astype(np.float32)
        
        return input_boxes, confidence, np.array(class_names)


class GroundingDinoSahiDetectionModel:
    """
    Класс для использования модели Grounding DINO и детекции объектов по частям изображении с использованием метода SAHI.
    """
   
    def __init__(
        self,
        base_model: GroundingDinoDetectionModel,
        slice_wh: tuple = (640, 640),
        overlap_ratio: tuple = (0.2, 0.2),
        iou_threshold: float = 0.3,
        nms_threshold: float = 0.15,
    ):
        self.base_model = base_model
        self.slice_wh = slice_wh
        self.overlap_ratio = overlap_ratio
        self.iou_threshold = iou_threshold
        self.nms_threshold = nms_threshold
    
    def update_threshold(
        self, 
        box_threshold: float = None, 
        text_threshold: float = None,
    ):
        if self.base_model:
            self.base_model.update_threshold(box_threshold=box_threshold, text_threshold=text_threshold)   

    def detect_objects(
        self,
        image: np.ndarray,
        texts: List[str],
    ) -> Dict[str, np.ndarray]:
        """
        Perform sliced inference on the image.
        """
        h, w, _ = image.shape
        caption = caption_list(texts)
        
        def inference_callback(image_slice: np.ndarray) -> sv.Detections:
            return self._inference_slice(image_slice, caption, texts)
        
        slicer = sv.InferenceSlicer(
            callback=inference_callback,
            slice_wh=self.slice_wh,
            overlap_wh=self.overlap_ratio,
            iou_threshold=self.iou_threshold,
        )
        
        detections = slicer(image=image)
        if len(detections) > 0:
            keep_indices = self._unique_nms(detections)
            keep_indices = keep_indices.cpu().numpy()
            if len(keep_indices) == 0:
                detections = sv.Detections.empty()
            else:
                detections = detections[keep_indices]
        class_names = [texts[cid] if cid < len(texts) else "unknown" for cid in detections.class_id]
        
        result = {
            'xyxy': detections.xyxy,
            'class': class_names,
            'confidence': detections.confidence,
        }
        return filter_oversized_objects(
            detections=result, 
            image_shape=(h, w), 
            max_area_ratio=0.62
        )
    
    def _inference_slice(
        self, 
        image_slice: np.ndarray, 
        caption: str,
        texts,
    ) -> sv.Detections:
        """Internal method to process a single slice"""
        h, w, _ = image_slice.shape
        image_tensor = self.base_model._transform_image(image_slice)
        boxes, logits, phrases = self.base_model._run_inference(image_tensor, caption)
        
        if len(boxes) == 0:
            return sv.Detections.empty()
        
        boxes_xyxy = boxes * torch.Tensor([w, h, w, h])
        boxes_xyxy = box_convert(boxes=boxes_xyxy, in_fmt="cxcywh", out_fmt="xyxy")
        
        class_ids = []
        for phrase in phrases:
            matched = False
            for idx, text in enumerate(texts):
                if text.lower() in phrase.lower() or phrase.lower() in text.lower():
                    class_ids.append(idx)
                    matched = True
                    break
            if not matched:
                class_ids.append(-1)

        class_ids = np.array(class_ids, dtype=np.int32)
        return sv.Detections(
            xyxy=boxes_xyxy.cpu().numpy(),
            confidence=logits.cpu().numpy(),
            class_id=class_ids,
        )
    
    def _unique_nms(self, detections: sv.Detections) -> torch.Tensor:
        """
        Применяет NMS отдельно для каждого класса.
        Возвращает индексы для фильтрации.
        """
        if len(detections) == 0:
            return torch.tensor([], dtype=torch.long)
        
        keep_indices = []
        unique_classes = list(set(detections.class_id))

        for class_id in unique_classes:
            # Пропускаем unknown классы (-1)
            if class_id == -1:
                continue
                
            class_indices = [i for i, cid in enumerate(detections.class_id) if cid == class_id]
            if len(class_indices) == 0:
                continue
                
            class_boxes = torch.tensor(detections.xyxy[class_indices], dtype=torch.float32)
            class_scores = torch.tensor(detections.confidence[class_indices], dtype=torch.float32)
            nms_keep = nms(
                boxes=class_boxes,
                scores=class_scores,
                iou_threshold=self.nms_threshold,
            )
            keep_indices.extend([class_indices[i] for i in nms_keep])
        
        return torch.tensor(keep_indices, dtype=torch.long)
    
    def visualization(
        self, 
        image: np.ndarray, 
        texts: List[str] = ["build", "car"]
    ) -> np.ndarray:
        """
        Визуализирует результат детекции на изображении.
        Возвращает аннотированное изображение (numpy array).
        """
        # Получаем детекции
        image_det = image.copy()
        detections_dict = self.detect_objects(image=image_det, texts=texts)

        phrases = detections_dict['class']
        unique_phrases = sorted(list(set(phrases)))
        class_map = {phrase: i for i, phrase in enumerate(unique_phrases)}
        class_ids = np.array([class_map[phrase] for phrase in phrases])
        
        detections = sv.Detections(xyxy=detections_dict['xyxy'], class_id=class_ids)
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator(text_position=sv.Position.CENTER)

        # Генерация лейблов
        labels = [
            f"{phrase} {logit:.2f}"
            for phrase, logit
            in zip(detections_dict["class"], detections_dict["confidence"])
        ]

        annotated_frame = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        annotated_image = box_annotator.annotate(scene=annotated_frame, detections=detections)
        annotated_image = label_annotator.annotate(scene=annotated_image, detections=detections, labels=labels)

        return annotated_image

    def cleanup(self):
        self.base_model.cleanup()

    def to_sam2_input(self, detections_dict: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Конвертирует результаты детекции в формат, совместимый с SAM2.
        
        Returns:
            Tuple[np.ndarray, np.ndarray, np.ndarray]: 
                - input_boxes: bounding boxes в формате xyxy (numpy array)
                - confidences: массив уверенностей
                - class_names: список названий классов
        """
        xyxy = detections_dict['xyxy']
        confidence = detections_dict['confidence']
        class_names = detections_dict['class']
        
        # SAM2 ожидает boxes в формате xyxy как numpy array
        input_boxes = xyxy.astype(np.float32)
        
        return input_boxes, confidence, np.array(class_names)
