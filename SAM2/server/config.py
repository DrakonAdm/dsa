from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "detection-user"
    MINIO_SECRET_KEY: str = "DetectionPass123!"
    MINIO_BUCKET: str = "images"
    MINIO_INPUT_PREFIX: str = "upload/original"
    MINIO_OUTPUT_PREFIX: str = "output"
    MINIO_SECURE: bool = False  # использовать True для production с HTTPS

    MINIO_LIVE_PATH: int = 12 # кол-во часов жизни ссылки на работу с маской
    # Таймауты и повторные попытки
    MINIO_REQUEST_TIMEOUT: int = 30
    MINIO_MAX_RETRIES: int = 3

    # Модели
    GROUNDING_DINO_CONFIG: str = "Grounded-SAM-2/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py"
    GROUNDING_DINO_WEIGHTS: str = "Grounded-SAM-2/gdino_checkpoints/groundingdino_swint_ogc.pth"
    SAM2_CONFIG: str = "configs/sam2.1/sam2.1_hiera_b+.yaml"
    SAM2_CHECKPOINT: str = "./Grounded-SAM-2/checkpoints/sam2.1_hiera_base_plus.pt"
    
    # Параметры детекции
    BOX_THRESHOLD: float = 0.20
    TEXT_THRESHOLD: float = 0.15
    NMS_THRESHOLD: float = 0.22
    SAHI_SLICE_WH: tuple = (640, 640)
    SAHI_OVERLAP: tuple = (0.2, 0.2)
    
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
    API_HOST: str = "localhost"
    API_PORT: int = 8001
    WORKERS: int = 1  # 1 воркер для исключения гонки моделей
    SHARE_GROUNDING_DINO_MODEL: bool = True # на сегментацию и детекцию используется только одна модель
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
    

settings = get_settings()