import os
import gc
import torch
import PIL.Image
import numpy as np
import supervision as sv
from mmengine import Config
from torchvision.ops import nms
from mmengine.runner import Runner
from torch.cuda.amp import autocast
from mmengine.dataset import Compose

from server.config import settings


class YoloWorldDetectionModel:
    """Класс для загрузки модели и детекции объектов на изображениях."""

    def __init__(
            self,
            config_path: str = settings.YoloWorld_CONFIG, 
            weights_path: str = settings.YoloWorld_WEIGHTS, 
            score_thr=settings.SCORE_THRESHOLD,
            nms_thr=settings.NMS_THRESHOLD,
            max_num_boxes=200,
            device=settings.DEVICE,
        ):
        self.score_thr = score_thr
        self.nms_thr = nms_thr
        self.max_num_boxes = max_num_boxes
        self.config_path = config_path
        self.weights_path = weights_path
        self.device = device

        # Загрузка модели
        try:
            self.cfg = Config.fromfile(config_path)
            self.cfg.device = device
            self.cfg.log_level = "ERROR"
            self.cfg.work_dir = os.path.abspath(f"./YoloWorld/log_error")
            self.cfg.load_from = weights_path

            self.runner = Runner.from_cfg(self.cfg)
            self.runner.model.to(device)
            checkpoint = torch.load(weights_path, map_location=device)
            self.runner.model.load_state_dict(checkpoint['state_dict'], strict=False)
            self.runner.model.eval()
            self.pipeline = Compose(self.cfg.test_dataloader.dataset.pipeline)

            self.runner.model.eval()
        except Exception as e:
            raise e

    def detect_objects(
        self, 
        frame, 
        texts: list[str] = [["build"], ["car"], [" "]],
        is_delete_large: bool = False,
        is_delete_include: bool = False,
    ):
        """Обрабатывает кадр и выполняет детекцию объектов."""
        print("Обрабатываем кадр")

        pred_instances, data_info = self.prediction_instances(frame=frame, texts=texts)

        # print(next(self.runner.model.parameters()).device)

        keep_idxs = nms(
            pred_instances.bboxes, 
            pred_instances.scores, 
            iou_threshold=self.nms_thr
        )
        pred_instances = pred_instances[keep_idxs]
        pred_instances = pred_instances[pred_instances.scores.float() > self.score_thr]

        if len(pred_instances.scores) > self.max_num_boxes:
            indices = pred_instances.scores.float().topk(self.max_num_boxes)[1]
            pred_instances = pred_instances[indices]

        pred_instances = pred_instances.cpu().numpy()

        """Удаление (неверных) объектов размером с 0.8 кадра и более"""
        mask = [True] * len(pred_instances['bboxes'])
        if is_delete_large:
            mask = self.__removal_large_obj(pred_instances['bboxes'], data_info)
        if is_delete_include:
            mask = self.__remove_obj_include_objects(pred_instances['bboxes'], mask)

        """Удаляем временную папку после завершения работы"""
        # shutil.rmtree("YoloWorld/log_error", ignore_errors=True)

        return {
            'xyxy': pred_instances['bboxes'][mask], 
            'class': self._reform_classes(
                labels=pred_instances['labels'][mask],
                texts=texts
            ), 
            'confidence': pred_instances['scores'][mask]
        }

    def _reform_classes(self, labels: list, texts: list[str] = [["build"], ["car"], [" "]],) -> list[str]:
        classes = []
        for label in labels:
            classes.append(texts[int(label)][0])
        return  classes

    def prediction_instances(
        self, 
        frame, 
        texts: list[str] = [["build"], ["car"], [" "]],
    ):
        if isinstance(frame, str):
            data_info = self.pipeline(dict(img_id=0, img_path=frame, texts=texts))
        else:
            try:
                """Если передан не путь до изображения, то передаём изображение и пустой путь"""
                data_info = self.dict_pipeline(
                    img_id=0, 
                    img=frame, 
                    img_path='none', 
                    texts=texts
                )
            except Exception as e:
                print(f'{e}')

        data_batch = dict(
            inputs=data_info["inputs"].unsqueeze(0),
            data_samples=[data_info["data_samples"]],
        )

        print("Запуск модели")
        with autocast(enabled=False), torch.no_grad():
            output = self.runner.model.test_step(data_batch)[0]
            self.runner.model.class_names = texts
            pred_instances = output.pred_instances

        return (pred_instances, data_info)

    def get_model_size(self):
        """Размер модели в памяти"""
        param_size = 0
        for param in self.runner.model.parameters():
            param_size += param.nelement() * param.element_size()
        buffer_size = 0
        for buffer in self.runner.model.buffers():
            buffer_size += buffer.nelement() * buffer.element_size()

        size_all_mb = (param_size + buffer_size) / (1024 ** 2)
        return size_all_mb

    @staticmethod
    def __get_size_image(data_info):
        high, width = data_info.get('data_samples').ori_shape[0:2]
        return high, width

    # def __removal_large_obj(
    #     self, 
    #     boxes, 
    #     data_info, 
    #     size: float | None = 0.8
    # ):
    #     """Удаление объекта большого размера"""
    #     high, width = self.__get_size_image(data_info)
    #     return [
    #         not (box[2] - box[0] > size * width and box[3] - box[1] > size * high)
    #         for box in boxes
    #     ]

    @staticmethod
    def __remove_obj_include_objects(
        boxes, 
        mask, 
        quantity: int | None = 2
    ):
        """Удаление объекта с включенными внутрь другими объектами"""
        for i in range(len(boxes)):
            if not mask[i]:
                continue
            count_included = 0
            for j in range(len(boxes)):
                if not mask[i] or i == j:
                    continue
                if (boxes[i][0] < boxes[j][0] and boxes[i][1] < boxes[j][1] and
                        boxes[i][2] > boxes[j][2] and boxes[i][3] > boxes[j][3]):
                    count_included += 1
            mask[i] = count_included < quantity
        return mask

    def __removal_large_obj(
        self, 
        boxes, 
        data_info, 
        size: float | None = 0.8,
        min_small_objects: int = 5
    ):
        """
        Удаление объектов большого размера.
        Фильтрация больших объектов активируется только если распознано 
        min_small_objects или более маленьких объектов.
        
        :param boxes: Список bounding box [x1, y1, x2, y2]
        :param data_info: Информация об изображении (для получения размеров)
        :param size: Порог размера объекта относительно изображения (0.8 = 80%)
        :param min_small_objects: Минимальное количество маленьких объектов для активации фильтрации
        :return: Список булевых значений (True = оставить объект, False = удалить)
        """
        high, width = self.__get_size_image(data_info)
        is_small_list = []
        is_large_list = []
        
        for box in boxes:
            box_width = box[2] - box[0]
            box_height = box[3] - box[1]
            is_large = (box_width > size * width and box_height > size * high)
            
            is_small_list.append(not is_large)
            is_large_list.append(is_large)
        
        small_objects_count = sum(is_small_list)
        if small_objects_count < min_small_objects:
            return [True] * len(boxes)
        
        return [not is_large for is_large in is_large_list]

    def cleanup(self):
        """Освобождает ресурсы модели"""
        try:
            if hasattr(self, 'runner'):
                if hasattr(self.runner, 'model'):
                    self.runner.model.to('cpu')

                if hasattr(self.runner, 'call_hook'):
                    self.runner.call_hook("after_run")

                del self.runner
        except Exception as e:
            print(f"Critical error during model cleanup: {e}")
        
        if hasattr(self, 'pipeline'):
            del self.pipeline
    
        gc.collect()

    def dict_pipeline(
        self,
        img,
        texts,
        img_id: int=0,
        img_path: str='slice',
    ) -> dict | None:
        return self.pipeline(dict(
            img_id=img_id, 
            img=img,
            img_path=img_path, 
            texts=texts
        ))  

    def visualization(
        self, 
        frame, 
        texts: list[str] = [["build"], ["car"], [" "]]
    ) -> np.array:
        """
        Визуализируем результат
        :param frame: путь до изображения или само изображение
        :param texts: список классов для распознавания
        :return:
        """
        print("Визуализируем анализ кадра")

        bounding_box_annotator = sv.BoundingBoxAnnotator()
        label_annotator = sv.LabelAnnotator(text_position=sv.Position.CENTER)

        detections = self.detect_objects(frame=frame, texts=texts)
        # Преобразуем словарь в объект Detections
        detections = sv.Detections(
            xyxy=detections["xyxy"],
            class_id=detections["class"],
            confidence=detections["confidence"]
        )

        # Генерация подписей
        labels = [
            f"{class_id} {confidence:0.3f}"
            for class_id, confidence
            in zip(detections.class_id, detections.confidence)
        ]

        if isinstance(frame, str):
            frame = PIL.Image.open(frame)

        svimage = np.array(frame)
        svimage = bounding_box_annotator.annotate(svimage, detections)
        # svimage = label_annotator.annotate(svimage, detections, labels)
        # sv.plot_image(svimage)

        return svimage
