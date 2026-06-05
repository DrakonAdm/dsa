from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException, status
from typing import List, AsyncGenerator, Tuple
from sqlalchemy import select
from pathlib import Path
from uuid import uuid4
from uuid import UUID
import numpy as np
import logging
import asyncio
import zipfile
import cv2
import io

from server.core.config import settings
from server.core.minio_client import minio_service
from server.core.dependencies import HandleMaskService
from server.service.transport.request.request import ImageUploadRequest
from server.service.application.class_type_service import ClassTypeService
from server.service.dal.repositories.project_repository import ProjectRepository
from server.service.dal.repositories import ImageRepository, AnnotationRepository, MaskRepository, ProjectRepository, ImageType, Image, User, UserType


class ImageService:
    @staticmethod
    async def _check_project_access(db: AsyncSession, user: User, project_id: str):
        project = await ProjectRepository.find_one_or_none(db, id=project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Проект не найден")
        
        is_member = await ProjectRepository.is_user_member(db, user.id, project_id)
        if not is_member and project.created_by_id != user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к проекту")
            
        return project

    @staticmethod
    async def upload_images(
        db: AsyncSession, 
        user: User, 
        project_id: str, 
        metadata: List[ImageUploadRequest], 
        files: List[UploadFile],
        mask_files: List[UploadFile],
        logger: logging.Logger,
        minio_service = minio_service,
    ):
        try:
            await ImageService._check_project_access(db, user, project_id)

            # проверка лимитов
            active_images = await ImageRepository.find_all(
                db, project_id=project_id, type_subscriptions=ImageType.active
            )
            limit = settings.USER_GROUP.MAX_IMG_LOAD if user.type_subscriptions == UserType.premium else settings.USER_GROUP.MIN_IMG_LOAD
            if len(active_images) + len(files) > limit:
                raise HTTPException(status_code=400, detail=f"Превышен лимит изображений (макс: {limit})")

            # сбор всех class_name для пакетной проверки/создания
            all_class_names = []
            for data in metadata:
                all_class_names.extend([ann.class_name for ann in data.annotations])
                all_class_names.extend([msk.class_name for msk in data.masks])
            name_to_en = await ClassTypeService.ensure_and_map_class_types(db, project_id, all_class_names, logger)


            created_images = []
            mask_file_idx = 0

            for data, file in zip(metadata, files):
                # Читаем байты изображения
                img_bytes = await file.read()
                ext = Path(file.filename or "image.jpg").suffix or ".jpg"
                unique_name = f"{uuid4()}{ext}"

                # загрузка оригинала в MinIO (в потоке, чтобы не блокировать)
                relative_img_path = f"{project_id}/{unique_name}"
                original_path = f"{settings.MINIO.INPUT_ORIGINAL_PREFIX}/{relative_img_path}"
                await asyncio.to_thread(
                    minio_service.upload_image, 
                    original_path, img_bytes, file.content_type or "image/jpeg"
                )

                img_data = data.model_dump(exclude={'annotations', 'masks'})
                img_data['file_path'] = relative_img_path
                img = ImageRepository.create(db, user_id=user.id, project_id=project_id, **img_data)
                await db.flush()

                for ann in data.annotations:
                    ann_dict = ann.model_dump()
                    ann_dict['class_name'] = name_to_en.get(ann.class_name, ann.class_name)
                    AnnotationRepository.create(db, image_id=img.id, **ann_dict)

                for msk_meta in data.masks:
                    if mask_file_idx < len(mask_files):
                        msk_file = mask_files[mask_file_idx]
                        msk_bytes = await msk_file.read()

                        try:
                            # CV2 и HandleMaskService блокирующие → запускаем в потоке
                            polygons = await asyncio.to_thread(
                                ImageService._decode_and_process_mask, 
                                msk_bytes
                            )
                        except Exception as e:
                            logger.warning(f"Ошибка обработки маски для {unique_name}: {e}")
                            polygons = []  # При ошибке пропускаем генерацию полигонов, но сохраняем файл маски

                        # путь для маски в MinIO
                        mask_path = f"{settings.MINIO.INPUT_SEGMENTATION_PREFIX}/{project_id}/{unique_name.replace(ext, '_mask.png')}"
                        await asyncio.to_thread(
                            minio_service.upload_image,
                            mask_path, msk_bytes, msk_file.content_type or "image/png"
                        )

                        # Сохраняем запись маски
                        msk_data = msk_meta.model_dump()
                        msk_data['file_path'] = mask_path
                        msk_data['class_name'] = name_to_en.get(msk_meta.class_name, msk_meta.class_name)
                        MaskRepository.create(db, image_id=img.id, **msk_data)

                        # создаём сегментационные аннотации из полигонов
                        for poly in polygons:
                            if not poly or len(poly) < 3: 
                                continue  # Пропускаем вырожденные полигоны
                            AnnotationRepository.create(
                                db,
                                image_id=img.id,
                                type='segment',
                                class_name=name_to_en.get(msk_meta.class_name, msk_meta.class_name),
                                data=poly
                            )
                        mask_file_idx += 1
                    else:
                        logger.warning(f"Нет файла маски для метаданных у изображения {unique_name}")

                created_images.append(img.id)
            return ImageService._serialize_images_for_response(
                await ImageRepository.reload_list_image_upload(
                    db=db, 
                    created_images=created_images
                )
            )

        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при загрузке изображений: {e}")
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при загрузке")

    @staticmethod
    def _serialize_images_for_response(images: list[Image]) -> list[dict]:
        """
        Конвертирует список ORM-объектов Image в список dict,
        готовых для сериализации в ImageResponse.
        """
        result = []
        for img in images:
            # Конвертируем аннотации: list[Annotation] → Dict[UUID, dict]
            annotations_dict = {}
            if img.annotations:  # уже загружено через selectinload
                for ann in img.annotations:
                    if ann.id is not None:
                        ann_data = {
                            'id': ann.id,
                            'type': getattr(ann, 'type', 'detect'),
                            'class_name': getattr(ann, 'class_name', ''),
                            'data': getattr(ann, 'data', {})
                        }
                        # Нормализация типа (как в валидаторе AnnotationResponse)
                        ann_type = ann_data['type']
                        if hasattr(ann_type, 'value'):
                            ann_type = ann_type.value
                        ann_data['type'] = {
                            'detection': 'detect',
                            'segmentation': 'segment'
                        }.get(ann_type, ann_type)
                        
                        annotations_dict[str(ann.id)] = ann_data
            
            result.append({
                'id': img.id,
                "file_path": img.file_path,
                'width': getattr(img, 'width', None),
                'height': getattr(img, 'height', None),
                'format': getattr(img, 'format', None),
                'annotations': annotations_dict
            })
        return result

    @staticmethod
    def _decode_and_process_mask(mask_bytes: bytes) -> List[List[List[float]]]:
        """Синхронная обёртка для CV2 (выполняется в пуле потоков)"""
        arr = np.frombuffer(mask_bytes, dtype=np.uint8)
        mask_img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        if mask_img is None:
            raise ValueError("Не удалось декодировать файл маски")
        return HandleMaskService.process_mask(mask_image=mask_img)
    
    @staticmethod
    async def get_project_images(db: AsyncSession, user: User, project_id: UUID, logger: logging.Logger) -> List[Image]:
        await ImageService._check_project_access(db, user, project_id)
        logger.info(f"Загрузка изображений для проекта {project_id}")
        return ImageService._serialize_images_for_response(
            await ImageRepository.find_by_project_with_annotations(
                db, 
                project_id)
        )

    @staticmethod
    async def get_image_by_id(db: AsyncSession, image_id: UUID, project_id: UUID, logger: logging.Logger):
        # Проверка доступа уже сделана в роутере, здесь только поиск
        return await ImageRepository.find_one_or_none(
            db, id=image_id, project_id=project_id, type_subscriptions="active"
        )

    @staticmethod
    async def get_images_by_ids(db: AsyncSession, project_id: UUID, image_ids: List[UUID], logger: logging.Logger):
        return await ImageRepository.find_by_ids_and_project(db, project_id, image_ids)

    @staticmethod
    def _resolve_object_key(file_path: str) -> str:
        """Преобразует относительный путь из БД в полный ключ для MinIO."""
        path = file_path.lstrip('/')
        if path.startswith(settings.MINIO.INPUT_ORIGINAL_PREFIX):
            return path
        return f"{settings.MINIO.INPUT_ORIGINAL_PREFIX}/{path}"
    
    @staticmethod
    async def stream_minio_file(
        db: AsyncSession, user, project_id: UUID, image_id: UUID, logger: logging.Logger
    ) -> Tuple[AsyncGenerator[bytes, None], str, str]:
        """Возвращает: (генератор_байт, content_type, имя_файла)"""
        await ImageService._check_project_access(db, user, project_id)
        
        img = await ImageRepository.find_one_or_none(
            db, id=image_id, project_id=project_id, type_subscriptions="active"
        )
        if not img:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")

        object_key = ImageService._resolve_object_key(img.file_path)
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg", 
            "png": "image/png", 
            "tiff": "image/tiff", 
            "webp": "image/webp"
        }
        content_type = mime_map.get(img.format.lower() if img.format else "", "application/octet-stream")
        filename = f"{img.id}.{img.format or 'jpg'}"

        return minio_service.stream_object(object_key), content_type, filename

    @staticmethod
    async def stream_zip_from_minio(
        db: AsyncSession, user, project_id: UUID, image_ids: List[UUID], logger: logging.Logger
    ) -> Tuple[AsyncGenerator[bytes, None], str, str]:
        """Возвращает: (генератор_zip_байт, content_type, имя_архива)"""
        await ImageService._check_project_access(db, user, project_id)

        images = await ImageRepository.find_by_ids_and_project(db, project_id, image_ids)
        if not images:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображения не найдены")

        async def _zip_generator() -> AsyncGenerator[bytes, None]:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for img in images:
                    try:
                        data = await asyncio.to_thread(
                            minio_service.download_image,
                            filename=img.file_path,
                            main_path=settings.MINIO.INPUT_ORIGINAL_PREFIX
                        )

                        if data is None:
                            logger.warning(f"Файл {img.file_path} недоступен в MinIO, пропускается при архивации")
                            continue

                        zf.writestr(f"{img.id}.{img.format or 'jpg'}", data)
                    except Exception as e:
                        logger.warning(f"Ошибка при упаковке {img.id} в ZIP: {e}")

            buf.seek(0)
            # Потоковая отдача собранного архива чанками по 8КБ
            while chunk := buf.read(8192):
                yield chunk

        return _zip_generator(), "application/zip", f"project_{project_id}_images.zip"

    @staticmethod
    async def soft_delete_image(db, user: User, project_id, image_id, logger: logging.Logger):
        await ImageService._check_project_access(db, user, project_id)

        img = await ImageRepository.find_one_or_none(db, id=image_id)
        if not img or img.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")

        success = await ImageRepository.update_by_id(
            db, image_id, type_subscriptions=ImageType.delete
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при удалении")
        
        return {"detail": "Изображение успешно удалено"}