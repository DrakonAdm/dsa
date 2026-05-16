import cv2
import random
import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon, LineString
from shapely.ops import split

import cv2
import numpy as np
from scipy import ndimage
from typing import List

class HandleMaskService:
    @staticmethod
    def process_mask(
        mask_image: np.ndarray, 
        min_object_area: int = None,
        area_ratio: float = 0.3,
        epsilon_factor: float = 0.001
    ) -> List[List[List[float]]]:
        h, w = mask_image.shape[:2]
        gray = cv2.cvtColor(mask_image, cv2.COLOR_RGB2GRAY) if len(mask_image.shape) == 3 else mask_image
        _, binary_mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
        
        # Динамический расчёт min_object_area
        if min_object_area is None:
            areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, num_labels)]
            if not areas:
                return []  # Объектов не найдено
            avg_area = sum(areas) / len(areas)
            # Порог = заданная доля от среднего, но не меньше 50 пикселей
            min_object_area = max(50, int(avg_area * area_ratio))

        # Фильтрация по площади
        clean_mask = np.zeros_like(binary_mask)
        for i in range(1, num_labels):
            if stats[i, cv2.CC_STAT_AREA] >= min_object_area:
                clean_mask[labels == i] = 255

        # Заполнение внутренних дыр
        filled_mask = ndimage.binary_fill_holes(clean_mask > 0).astype(np.uint8) * 255

        # Извлечение контуров
        # CHAIN_APPROX_NONE сохраняет ВСЕ точки контура (вместо SIMPLE)
        contours, _ = cv2.findContours(filled_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        polygons = []
        for contour in contours:
            epsilon = epsilon_factor * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            points = approx.reshape(-1, 2).tolist()
            
            # Нормализация координат
            norm_points = [[round(x / w, 6), round(y / h, 6)] for x, y in points]
            polygons.append(norm_points)
            
        return polygons
    
    @staticmethod
    def draw_polygons_on_image(image: np.ndarray, polygons: list[list[list[float]]], save_path: str = None) -> np.ndarray:
        """
        Отрисовывает полигоны на изображении с полупрозрачной заливкой и подписями.
        
        :param image: Исходное изображение (np.ndarray)
        :param polygons: Список полигонов от process_mask()
        :param save_path: Путь для сохранения результата (опционально)
        :return: Изображение с нарисованными полигонами
        """
        if not polygons:
            print("Полигоны не найдены.")
            return image

        h, w = image.shape[:2]
        vis_img = image.copy()

        for idx, poly in enumerate(polygons):
            abs_poly = [[int(x * w), int(y * h)] for x, y in poly]
            pts = np.array(abs_poly, dtype=np.int32).reshape((-1, 1, 2))
            color = tuple(random.choices(range(256), k=3))

            overlay = vis_img.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.35, vis_img, 0.65, 0, vis_img)
            cv2.polylines(vis_img, [pts], isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA)

            M = cv2.moments(pts)
            if M["m00"] != 0:
                cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                cv2.putText(vis_img, str(idx), (cx, cy), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        if save_path:
            cv2.imwrite(save_path, vis_img)
            print(f"Изображение сохранено: {save_path}")
            
        return vis_img

    @staticmethod
    def split_polygon(polygon: list[list[float]], cut_points: list[list[float]]) -> list[list[list[float]]]:
        """
        Разделяет один полигон на два по заданной линии разреза.
        
        :param polygon: Полигон в формате [[x, y], ...] (координаты нормализованы [0, 1])
        :param cut_points: Точки, задающие линию разреза. Минимум 2 точки.
        :return: Список из двух полигонов в том же формате.
        """
        if len(cut_points) < 2:
            raise ValueError("Для задания линии разреза требуется минимум 2 точки.")

        poly = Polygon(polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)  # автоисправление самопересечений, если есть

        p1, p2 = cut_points[0], cut_points[-1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        if dx == 0 and dy == 0:
            raise ValueError("Начальная и конечная точки разреза совпадают.")

        # расширяем линию за пределы [0, 1], чтобы гарантированно пересечь границы полигона
        extend_factor = 2.0
        line_start = [p1[0] - dx * extend_factor, p1[1] - dy * extend_factor]
        line_end = [p2[0] + dx * extend_factor, p2[1] + dy * extend_factor]
        cut_line = LineString([line_start, line_end])

        if not poly.intersects(cut_line):
            raise ValueError("Линия разреза не пересекает полигон.")

        result = split(poly, cut_line)

        # Shapely может вернуть GeometryCollection или MultiPolygon
        parts = list(result.geoms) if hasattr(result, "geoms") else [result]

        if len(parts) != 2:
            raise ValueError(f"Разрез должен давать ровно 2 полигона, получено: {len(parts)}")

        # конвертируем обратно в нормализованный формат
        split_polygons = []
        for geom in parts:
            coords = list(geom.exterior.coords)[:-1]
            split_polygons.append([[round(x, 6), round(y, 6)] for x, y in coords])

        return split_polygons