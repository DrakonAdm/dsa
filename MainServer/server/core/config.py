import os
import sys
import json
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from server.service.db.shemas.models import ModelType 


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

CONFIG_FILE_PATH = BASE_DIR / "settings.json"


class DBSettings(BaseSettings):
    HOST: str
    PORT: int
    NAME: str
    USER: str
    PASSWORD: str
    
    @property
    def url(self) -> str:
        """Формирует PostgreSQL URL подключения"""
        return f"postgresql+asyncpg://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.NAME}"
    
    model_config = SettingsConfigDict(extra="ignore")


class TokenSettings(BaseSettings):
    REFRESH_TYPE: str = Field(alias="REFRESH_TYPE")
    ACCESS_TYPE: str = Field(alias="ACCESS_TYPE")
    ISSUER: str
    AUDIENCE: str
    model_config = SettingsConfigDict(extra="ignore")


class UserSecuritySettings(BaseSettings):
    TIME_LIVE_PASSWORD: int
    MAX_LOGIN_ATTEMPTS: int
    BLOCK_TIME_MINUTES: int
    model_config = SettingsConfigDict(extra="ignore")


class AllowedSettings(BaseSettings):
    IPS: list[str] = Field(default_factory=list)
    model_config = SettingsConfigDict(extra="ignore")


class ModelConfigItem(BaseModel):
    """Элемент конфигурации модели для инициализации БД"""
    name: str
    type: ModelType
    endpoint_url: str
    is_active: bool = True
    
    @field_validator("is_active", mode="before")
    @classmethod
    def parse_bool(cls, value):
        """Конвертирует 'True'/'False'/1/0 в bool"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)


class AdminAuthSettings(BaseSettings):
    """Настройки админ-панели и аутентификации из .env"""
    ADMIN_USERNAME: str | None = None
    ADMIN_USERNAME2: str | None = None
    ADMIN_HASHED_PASSWORD: str | None = None
    ADMIN_HASHED_PASSWORD2: str | None = None
    SESSION_SECRET: str | None = None
    AUTH_SECRET: str | None = None
    AUTH_ALGORITHM: str = "HS256"
    
    model_config = SettingsConfigDict(extra="ignore")


class MinioSettings(BaseSettings):
    """Настройки MinIO"""
    ENDPOINT: str = "localhost:9000"
    ACCESS_KEY: str = "main-service"
    SECRET_KEY: str = "MainServicePass123!"
    BUCKET: str = "images"
    INPUT_ORIGINAL_PREFIX: str = "upload/original"
    INPUT_SEGMENTATION_PREFIX: str = "upload/segmentation"
    OUTPUT_PREFIX: str = "output"
    SECURE: bool = False  # использовать True для production с HTTPS

    LIVE_PATH: int = 12 # кол-во часов жизни ссылки на работу с маской
    # Таймауты и повторные попытки
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3

class UserProjectSettings(BaseSettings):
    MAX_GROUP_CREATED: int = 99
    MIN_GROUP_CREATED: int = 3
    MAX_GROUP_PARTICIPATED: int = 199
    MIN_GROUP_PARTICIPATED: int = 5

    MIN_IMG_LOAD: int = 10
    MAX_IMG_LOAD: int = 1000

    MIN_IMG_ANALYZE: int = 5
    MAX_IMG_ANALYZE: int = 20

class AnalyzeSettings(BaseSettings):
    TOKEN_SECRET: str = 'huahcsaca'
    TOKEN_SALT: str = 'djj29xclq043ncqop'
    CALLBACK_BASE_URL: str = 'http://localhost:8085/api/analyze/analysis'
    MAX_QUEUE_SIZE: int = 250
    MAX_RETRIES: int = 2

class Settings(BaseSettings):
    """Глобальные настройки приложения"""
    # Server
    HOST: str
    PORT: int
    PROJECT_NAME: str = "Detection Segmentation Anything Server"
    
    # Вложенные секции из JSON
    DB: DBSettings
    TOKEN: TokenSettings
    USER: UserSecuritySettings
    ALLOWED: AllowedSettings
    
    # Model classes
    MODEL_CONFIG_DEFAULT: list[ModelConfigItem] = Field(default_factory=list)

    # Вложенная секция для админ-настроек
    ADMIN: AdminAuthSettings = Field(default_factory=AdminAuthSettings)

    # Minio
    MINIO: MinioSettings = Field(default_factory=MinioSettings)

    # restriction on groups User
    USER_GROUP: UserProjectSettings = Field(default_factory=UserProjectSettings)

    # Analyze
    ANALYZE: AnalyzeSettings = Field(default_factory=AnalyzeSettings)
    
    # CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        # отключаем загрузку из env для вложенных моделей,
        # если читать их только из JSON
        env_nested_delimiter="__",  # для env-переменных вида DB__HOST
    )
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_list(cls, value):
        """Парсинг строки в список для env-переменных"""
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return []
    
    @property
    def allowed_ips(self) -> list[str]:
        """Удобный доступ к списку разрешённых IP"""
        return self.ALLOWED.IPS
    
    @property
    def database_url(self) -> str:
        """Удобный доступ к URL базы данных"""
        return self.DB.url


def load_json_config() -> dict:
    """Загружает конфигурацию из JSON-файла с обработкой ошибок"""
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Конфигурационный файл не найден: {CONFIG_FILE_PATH}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ошибка парсинга JSON в {CONFIG_FILE_PATH}: {e}")


@lru_cache()
def get_settings() -> Settings:
    """Кэшированный инстанс настроек (singleton)"""
    json_config = load_json_config()
    return Settings(**json_config)


settings = get_settings()