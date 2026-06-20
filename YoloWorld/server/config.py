from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "detection-user-yolo"
    MINIO_SECRET_KEY: str = "DetectionYoloPass123!"
    MINIO_BUCKET: str = "images"
    MINIO_INPUT_PREFIX: str = "upload/original"
    MINIO_SECURE: bool = False  # использовать True для production с HTTPS

    MINIO_LIVE_PATH: int = 12 # кол-во часов жизни ссылки на работу с маской
    # Таймауты и повторные попытки
    MINIO_REQUEST_TIMEOUT: int = 30
    MINIO_MAX_RETRIES: int = 3

    # Модели
    YoloWorld_CONFIG: str = "./YOLOWorld/configs/pretrain/app_use_hug.py"
    YoloWorld_WEIGHTS: str = "./weights/weight.pth"
    
    # Параметры детекции
    BOX_THRESHOLD: float = 0.20
    SCORE_THRESHOLD: float = 0.025
    NMS_THRESHOLD: float = 0.15
    SAHI_SLICE_WH: tuple = (640, 640)
    SAHI_OVERLAP: tuple = (0.2, 0.2)

    TEXT_THRESHOLD: float = 0.15
    
    # Устройство
    DEVICE: str = "cpu"  # или "cuda" или "cpu"
    USE_BFLOAT16: bool = False

    # Callback
    CALLBACK_TIMEOUT_SEC: int = 30
    CALLBACK_MAX_RETRIES: int = 3
    CALLBACK_RETRY_DELAY_SEC: float = 5.0
    
    # Менеджер задач
    TASK_TIMEOUT_SEC: int = 300  # Общий таймаут выполнения задачи
    
    # Сервер
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8002
    WORKERS: int = 1  # 1 воркер для исключения гонки моделей
    SHARE_GROUNDING_DINO_MODEL: bool = True # на сегментацию и детекцию используется только одна модель
    INTERNAL_SERVICE_TOKEN: str = "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
    

settings = get_settings()