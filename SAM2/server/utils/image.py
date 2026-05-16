import cv2
import numpy as np
from PIL import Image
import io


def load_image_from_bytes(image_bytes: bytes) -> np.ndarray:
    """Конвертирует bytes изображения в OpenCV формат (BGR)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def encode_image_to_jpeg(image: np.ndarray, quality: int = 95) -> bytes:
    """Кодирует OpenCV изображение в JPEG bytes."""
    success, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise ValueError("Не удалось закодировать изображение")
    return buffer.tobytes()


def encode_mask_to_png(mask: np.ndarray) -> bytes:
    """
    Конвертирует бинарную маску (H, W) bool/uint8 в PNG bytes.
    
    Args:
        mask: numpy array формы (H, W), значения 0/1 или True/False
        
    Returns:
        bytes: PNG изображение в памяти
    """
    # Гарантируем uint8 (0 или 255)
    if mask.dtype == bool:
        mask_uint8 = (mask * 255).astype(np.uint8)
    else:
        mask_uint8 = np.clip(mask, 0, 255).astype(np.uint8)
    
    success, encoded = cv2.imencode('.png', mask_uint8, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not success:
        raise ValueError("Failed to encode mask to PNG")
    
    return encoded.tobytes()


def serialize_for_json(obj):
    """
    Рекурсивно преобразует numpy-типы в стандартные Python-типы для JSON.
    """
    import numpy as np
    
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, np.bytes_):
        return obj.decode('utf-8', errors='replace')
    return obj  # str, int, float, None и т.д.