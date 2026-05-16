import torch
import numpy as np
import cv2
import gc
from pathlib import Path
from typing import List, Dict, Union, Optional, Tuple, Literal
import supervision as sv
import pycocotools.mask as mask_util

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from server.models.groundingdino_model import GroundingDinoDetectionModel, GroundingDinoSahiDetectionModel


class GroundedSAM2Model:
    """
    Класс для сегментации изображений с использованием GroundingDINO + SAM2.
    
    Поддерживает два режима детекции:
    - 'full': обычная детекция на всём изображении
    - 'sahi': детекция по частям с использованием SAHI для больших изображений
    """
    
    def __init__(
        self,
        sam2_checkpoint: str,
        sam2_model_config: str,
        grounding_model: Union[GroundingDinoDetectionModel, GroundingDinoSahiDetectionModel],
        device: str = 'cpu',
        use_bfloat16: bool = True,
        multimask_output: bool = False,
    ):
        """
        Args:
            sam2_checkpoint: Путь к чекпоинту SAM2
            sam2_model_config: Путь к конфигу SAM2 (yaml)
            grounding_model: Экземпляр GroundingDinoDetectionModel или GroundingDinoSahiDetectionModel
            device: Устройство для вычислений ('cuda' или 'cpu')
            use_bfloat16: Использовать bfloat16 для ускорения (требуется Ampere+ GPU)
            multimask_output: Возвращать ли несколько масок на бокс (SAM2 параметр)
        """
        self.device = device
        self.use_bfloat16 = use_bfloat16
        self.multimask_output = multimask_output
        self.grounding_model = grounding_model

        print(f"Building SAM2 model from {sam2_checkpoint}...")
        self.sam2_model = build_sam2(
            config_file=sam2_model_config,
            ckpt_path=sam2_checkpoint,
            device=device
        )
        self.sam2_predictor = SAM2ImagePredictor(self.sam2_model)
        
        if device == 'cuda' and torch.cuda.is_available():
            if torch.cuda.get_device_properties(0).major >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                print("Enabled TF32 for Ampere GPU")
        
        print("GroundedSAM2Model initialized successfully.")
    
    def _prepare_sam2_input(
        self, 
        detections_dict: Dict[str, np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Подготовка входных данных для SAM2 из результатов GroundingDINO.
        
        Returns:
            input_boxes: np.ndarray (N, 4) в формате xyxy
            confidences: np.ndarray (N,)
            class_names: List[str]
        """
        return self.grounding_model.to_sam2_input(detections_dict)
    
    def _run_sam2_segmentation(
        self,
        image_source: np.ndarray,
        input_boxes: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Запуск SAM2 для получения масок по заданным боксам.
        
        Args:
            image_source: Исходное изображение в формате RGB numpy array
            input_boxes: Боксы в формате xyxy (numpy array)
            
        Returns:
            masks: np.ndarray (N, H, W) бинарные маски
            scores: np.ndarray (N,) скоры масок
        """
        self.sam2_predictor.set_image(image_source)
        if self.use_bfloat16 and self.device == 'cuda':
            autocast = torch.autocast(device_type='cuda', dtype=torch.bfloat16)
            autocast.__enter__()
        
        try:
            masks, scores, logits = self.sam2_predictor.predict(
                point_coords=None,
                point_labels=None,
                box=input_boxes,
                multimask_output=self.multimask_output,
            )
        finally:
            if self.use_bfloat16 and self.device == 'cuda':
                autocast.__exit__(None, None, None)
        
        if self.multimask_output and masks.ndim == 4:
            best_idx = np.argmax(scores, axis=1)
            masks = masks[np.arange(masks.shape[0]), best_idx]
            scores = scores[np.arange(scores.shape[0]), best_idx]
        
        if masks.ndim == 4:
            masks = masks.squeeze(1)
        
        return masks, scores
    
    def get_gd_model(self, ) -> GroundingDinoDetectionModel | GroundingDinoSahiDetectionModel:
        return self.grounding_model
    
    def segment(
        self,
        image: np.ndarray,
        texts: List[str],
        return_format: Literal['dict', 'supervision'] = 'dict',
    ) -> Union[Dict[str, np.ndarray], sv.Detections]:
        """
        Основной метод: детекция + сегментация.
        
        Args:
            image: Изображение в формате numpy array (H, W, C), RGB или BGR
            texts: Список текстовых запросов для GroundingDINO
            return_format: Формат возврата - 'dict' или 'supervision.Detections'
            
        Returns:
            Если return_format='dict':
                {
                    'xyxy': np.ndarray (N, 4),
                    'class': List[str],
                    'confidence': np.ndarray (N,),
                    'mask': np.ndarray (N, H, W) bool,
                    'mask_score': np.ndarray (N,)
                }
            Если return_format='supervision':
                sv.Detections с полями xyxy, mask, class_id, confidence
        """
        # Конвертация BGR -> RGB если нужно (OpenCV загружает в BGR)
        if image.ndim == 3 and image.shape[2] == 3:
            if cv2.cvtColor(image, cv2.COLOR_BGR2RGB).sum() != image.sum():
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image.copy()
        else:
            image_rgb = image.copy()
        
        detections_dict = self.grounding_model.detect_objects(
            image=image_rgb,
            texts=texts
        )
        
        if len(detections_dict['xyxy']) == 0:
            empty_result = {
                'xyxy': np.empty((0, 4)),
                'class': [],
                'confidence': np.empty((0,)),
                'mask': np.empty((0, *image.shape[:2]), dtype=bool),
                'mask_score': np.empty((0,))
            }
            return sv.Detections.empty() if return_format == 'supervision' else empty_result
        
        input_boxes, confidences, class_names = self._prepare_sam2_input(detections_dict)
        masks, mask_scores = self._run_sam2_segmentation(
            image_source=image_rgb,
            input_boxes=input_boxes
        )
        
        result = {
            'xyxy': detections_dict['xyxy'],
            'class': detections_dict['class'],
            'confidence': detections_dict['confidence'],
            'mask': masks.astype(bool),
            'mask_score': mask_scores,
        }
        
        if return_format == 'supervision':
            unique_classes = sorted(list(set(result['class'])))
            class_map = {cls: i for i, cls in enumerate(unique_classes)}
            class_ids = np.array([class_map[cls] for cls in result['class']], dtype=int)
            
            return sv.Detections(
                xyxy=result['xyxy'],
                mask=result['mask'],
                class_id=class_ids,
                confidence=result['confidence'],
                data={'class_name': result['class']} 
            )
        
        return result
    
    def visualize(
        self,
        image: np.ndarray,
        texts: List[str],
        show_boxes: bool = True,
        show_masks: bool = True,
        show_labels: bool = True,
    ) -> np.ndarray:
        """
        Визуализация результатов сегментации на изображении.
        
        Returns:
            Аннотированное изображение в формате BGR (для cv2.imshow / cv2.imwrite)
        """
        detections = self.segment(image=image, texts=texts, return_format='supervision')
        if len(detections) == 0:
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if image.ndim == 3 else image

        annotated = cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if image.ndim == 3 else image.copy()
        class_names = None
        if hasattr(detections, 'data') and isinstance(detections.data, dict):
            class_names = detections.data.get('class_name', None)
        
        if class_names is None:
            class_names = detections.class_id
            
        labels = [
            f"{cls} {conf:.2f}"
            for cls, conf in zip(class_names, detections.confidence)
        ] if show_labels else None
        
        # Аннотаторы supervision
        if show_boxes:
            box_annotator = sv.BoxAnnotator()
            annotated = box_annotator.annotate(scene=annotated, detections=detections)
        
        if show_labels and labels:
            label_annotator = sv.LabelAnnotator(text_position=sv.Position.CENTER)
            annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
        
        if show_masks and detections.mask is not None:
            mask_annotator = sv.MaskAnnotator()
            annotated = mask_annotator.annotate(scene=annotated, detections=detections)
        
        return annotated
    
    def export_to_coco_rle(self, masks: np.ndarray) -> List[Dict]:
        """
        Конвертация масок в формат RLE (COCO) для сохранения в JSON.
        
        Args:
            masks: np.ndarray (N, H, W) бинарные маски
            
        Returns:
            Список словарей в формате RLE
        """
        rles = []
        for mask in masks:
            rle = mask_util.encode(np.array(mask[:, :, None], order="F", dtype="uint8"))[0]
            rle["counts"] = rle["counts"].decode("utf-8")
            rles.append(rle)
        return rles
    
    def export_results(
        self,
        image_path: str,
        results: Dict[str, np.ndarray],
        output_path: Optional[str] = None,
    ) -> Dict:
        """
        Экспорт результатов в стандартный JSON-формат.
        
        Args:
            image_path: Путь к исходному изображению
            results: Словарь результатов из метода segment()
            output_path: Опциональный путь для сохранения JSON
            
        Returns:
            Словарь с результатами в JSON-совместимом формате
        """
        h, w = results['mask'].shape[1], results['mask'].shape[2] if len(results['mask']) > 0 else (0, 0)
        
        # Конвертация масок в RLE
        mask_rles = self.export_to_coco_rle(results['mask']) if len(results['mask']) > 0 else []
        
        annotations = [
            {
                "class_name": class_name,
                "bbox": box.tolist() if isinstance(box, np.ndarray) else box,
                "segmentation": mask_rle,
                "score": float(score),
                "mask_score": float(mask_score),
            }
            for class_name, box, mask_rle, score, mask_score in zip(
                results['class'],
                results['xyxy'],
                mask_rles,
                results['confidence'],
                results['mask_score']
            )
        ]
        
        export_data = {
            "image_path": str(image_path),
            "annotations": annotations,
            "box_format": "xyxy",
            "img_width": w,
            "img_height": h,
        }
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            print(f"Results saved to {output_path}")
        
        return export_data
    
    def cleanup(self):
        """Освобождение ресурсов: очистка кэша CUDA и удаление моделей."""
        # Очистка SAM2
        if hasattr(self, 'sam2_predictor'):
            del self.sam2_predictor
        if hasattr(self, 'sam2_model'):
            del self.sam2_model

        # Очистка GroundingDINO
        if hasattr(self.grounding_model, 'cleanup'):
            self.grounding_model.cleanup()
        
        # Сборка мусора и очистка CUDA
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        print("GroundedSAM2Model resources cleaned up.")
