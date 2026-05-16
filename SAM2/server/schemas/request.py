from pydantic import BaseModel, Field, field_validator
from typing import Optional

class DetectionRequest(BaseModel):
    """Запрос на детекцию/сегментацию."""
    image_path: str = Field(..., description="Путь к изображению в MinIO bucket")
    texts: list[str] = Field(..., description="Текстовые промпты для поиска", min_length=1)
    # box_threshold: Optional[float] = Field(None, ge=0, le=1, description="Порог для bounding box")
    # text_threshold: Optional[float] = Field(None, ge=0, le=1, description="Порог для текста")
    output_suffix: Optional[str] = Field(None, description="Суффикс для имени выходного файла")
    callback_url: Optional[str] = Field(None, description="API основного сервису, куда отправлять результат")
    task_id: Optional[str] = Field(..., description="ID задачи с основного сервиса")

    @field_validator('image_path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v or v.startswith(('http://', 'https://')):
            raise ValueError("image_path должен быть путём внутри MinIO bucket, не URL")
        return v.lstrip('/')

class DetectionResponse(BaseModel):
    """Ответ сервиса."""
    success: bool
    result_url: Optional[str] = Field(None, description="Presigned URL к результату в MinIO")
    detections: Optional[dict] = Field(None, description="Детали детекции (boxes, confidences)")
    processing_time_ms: float
    message: Optional[str] = None

class QueueStatusResponse(BaseModel):
    """Статус очередей задач."""
    shared: Optional[dict] = None
    detection: Optional[dict] = None
    segmentation: Optional[dict] = None

class DetectionCallbackResponse(BaseModel):
    success: bool
    is_segmentation: Optional[bool] = Field(None, description='Если ошибок нет без сегментации')
    result: Optional[dict] = Field(None, description='Словарь результата детекции и/или сегментации')
    processing_time_ms: float = 0
    model_type: Optional[str] = None  # "dino_standard", "sam2_sahi", etc.
    error: Optional[dict] = Field(None, description='Если есть ошибка')