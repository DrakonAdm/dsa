import io
import logging
from typing import AsyncGenerator
from minio import Minio
from urllib3 import PoolManager, Retry, Timeout
from minio.error import S3Error
from datetime import timedelta
import asyncio

from server.core.config import settings


logger = logging.getLogger(__name__)


class MinIOService:
    """Асинхронный сервис для работы с MinIO"""
    
    def __init__(self):
        # Настройка повторных попыток для устойчивости
        http_client = self._create_http_client()
        
        self.client = Minio(
            endpoint=settings.MINIO.ENDPOINT,
            access_key=settings.MINIO.ACCESS_KEY,
            secret_key=settings.MINIO.SECRET_KEY,
            secure=settings.MINIO.SECURE,
            http_client=http_client,
        )
        self.bucket = settings.MINIO.BUCKET
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Проверка существования бакета при инициализации"""
        if not self.client.bucket_exists(self.bucket):
            logger.error(f"Bucket {self.bucket} not found!")
            raise RuntimeError(f"Bucket {self.bucket} does not exist")
        
    def _create_http_client(self):
        """Создаёт urllib3.PoolManager с настройками таймаутов и retry"""        
        retry = Retry(
            total=settings.MINIO.MAX_RETRIES,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "PUT", "HEAD", "DELETE"]
        )
        
        timeout = Timeout(
            connect=10,  # таймаут подключения
            read=settings.MINIO.REQUEST_TIMEOUT,  # таймаут чтения
            total=settings.MINIO.REQUEST_TIMEOUT + 10  # общий таймаут
        )
        
        return PoolManager(
            retries=retry,
            timeout=timeout,
            block=True,
            maxsize=10  # пул соединений
        )
    
    def _build_path(self, prefix: str, filename: str) -> str:
        """Формирует объект-ключ в формате префикс/файл"""
        return f"{prefix.rstrip('/')}/{filename.lstrip('/')}"
    
    def download_image(self, filename: str, main_path: str = settings.MINIO.OUTPUT_PREFIX) -> bytes:
        """Скачивает изображение из MinIO."""
        object_path = self._build_path(main_path, filename)
        print(object_path)
        try:
            response = self.client.get_object(
                bucket_name=self.bucket, 
                object_name=object_path,
            )
            return response.read()
        except S3Error as e:
            logger.error(f"MinIO read error: {e}")
            return None
        finally:
            if 'response' in locals():
                response.close()
                response.release_conn()
    
    async def stream_object(self, object_name: str, chunk_size: int = 8192) -> AsyncGenerator[bytes, None]:
        """
        Асинхронно стримит объект из MinIO по полному ключу.
        """
        object_name = object_name.lstrip('/')
        
        response = await asyncio.to_thread(
            self.client.get_object, 
            bucket_name=self.bucket, 
            object_name=object_name
        )
        try:
            while chunk := await asyncio.to_thread(response.read, chunk_size):
                yield chunk
        finally:
            await asyncio.to_thread(response.close)
            await asyncio.to_thread(response.release_conn)
    
    def upload_image(self, object_path: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        """Загружает изображение в MinIO, возвращает публичный URL."""
        try:
            data = io.BytesIO(image_bytes)
            data.seek(0, 2)
            length = data.tell()
            data.seek(0)
            
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_path,
                data=data,
                length=length,
                content_type=content_type,
            )
            return object_path
        except S3Error as e:
            raise ValueError(f"Ошибка загрузки в MinIO: {e}")
    
    def generate_result_path(self, original_path: str, suffix: str, main_path: str = settings.MINIO.INPUT_ORIGINAL_PREFIX) -> str:
        """
        Генерирует путь для результата, сохраняя опциональный префикс клиента.
        main_path = settings.MINIO.INPUT_ORIGINAL_PREFIX or settings.MINIO.INPUT_SEGMENTATION_PREFIX
        
        Примеры:
            "name_image.jpg" → "output/name_image_suffix.jpg"
            "jfgvdsfbkzvhg/name_image.jpg" → "output/jfgvdsfbkzvhg/name_image_suffix.jpg"
            "a1b2c3/subfolder/img.png" → "output/a1b2c3/subfolder/img_suffix.png"
        """
        from pathlib import PurePosixPath
        
        original_path = original_path.strip('/')
        if not original_path:
            raise ValueError("original_path cannot be empty")
        
        parts = original_path.split('/')
        filename = parts[-1]
        path_obj = PurePosixPath(filename)
        new_filename = f"{path_obj.stem}_{suffix}{path_obj.suffix}"
        
        if len(parts) > 1:
            client_prefix = '/'.join(parts[:-1])
            return f"{main_path}/{client_prefix}/{new_filename}"
        else:
            return f"{main_path}/{new_filename}"
