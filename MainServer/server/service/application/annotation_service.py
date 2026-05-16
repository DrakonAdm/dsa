from fastapi import HTTPException
from pathlib import Path
import asyncio
import logging
import io
from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID
import numpy as np
from PIL import Image as PilImage
from sqlalchemy.ext.asyncio import AsyncSession

from server.core.minio_client import minio_service
from server.core.dependencies import HandleMaskService
from server.core.config import settings
from server.service.transport.request.request import AnnotationCreate, AnnotationBatchUpdate
from server.service.dal.repositories import (
    AnnotationRepository, ProjectRepository, ClassTypeRepository, ImageRepository, MaskRepository, 
    User, Annotation, AnnotationType, Mask
)

logger = logging.getLogger(__name__)


class AnnotationService:
    @staticmethod
    async def _verify_access(db, user_id, project_id, image_id):
        """Проверяет участие в проекте и существование изображения в этом проекте."""
        is_member = await ProjectRepository.is_user_member(db, user_id, project_id)
        if not is_member:
            raise HTTPException(status_code=403, detail="Нет доступа к проекту")
            
        image = await ImageRepository.find_one_or_none(db, id=image_id, project_id=project_id)
        if not image:
            raise HTTPException(status_code=404, detail="Изображение не найдено в данном проекте")
        return image

    @staticmethod
    async def _resolve_class_names_to_ru(db, project_id: UUID, class_names: List[str]) -> Dict[str, str]:
        """
        Валидирует классы и возвращает маппинг {входное_имя: name_ru}.
        Если имя уже русское, маппинг оставит его без изменений.
        """
        if not class_names:
            return {}
        unique_names = list(set(class_names))
        existing = await ClassTypeRepository.find_existing_by_names(db, project_id, unique_names)
        
        name_to_ru = {}
        valid_names = set()
        for ct in existing:
            valid_names.add(ct.name_ru)
            valid_names.add(ct.name_eng)
            # Маппинг в обе стороны: и ru, и eng -> name_ru
            name_to_ru[ct.name_ru] = ct.name_ru
            name_to_ru[ct.name_eng] = ct.name_ru
            
        invalid = [name for name in unique_names if name not in valid_names]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Классы не найдены в проекте: {invalid}")
            
        return name_to_ru

    @classmethod
    async def get_by_image(cls, db, user, project_id, image_id) -> List:
        await cls._verify_access(db, user.id, project_id, image_id)
        return await AnnotationRepository.get_by_image_id(db, image_id)

    @classmethod
    async def create(cls, db, user: User, project_id, image_id, data: AnnotationCreate) -> Annotation:
        await cls._verify_access(db, user.id, project_id, image_id)
        name_to_ru = await cls._resolve_class_names_to_ru(db, project_id, [data.class_name])
        return await AnnotationRepository.async_create(
            db,
            image_id=image_id,
            type=data.type,
            class_name=name_to_ru[data.class_name],
            data=data.data,
            is_selected=False
        )

    @classmethod
    async def create_batch(cls, db, user: User, project_id, image_id, data_list: List[AnnotationCreate]) -> List[Annotation]:
        await cls._verify_access(db, user.id, project_id, image_id)
        names = [d.class_name for d in data_list]
        name_to_ru = await cls._resolve_class_names_to_ru(db, project_id, names)
        new_anns = [
            Annotation(
                image_id=image_id, 
                type=d.type, 
                class_name=name_to_ru[d.class_name], 
                data=d.data
            ) for d in data_list
        ]
        return await AnnotationRepository.create_many(db, new_anns)

    @classmethod
    async def update_single(cls, db, user: User, project_id, image_id, ann_id, update_data: dict) -> Annotation:
        await cls._verify_access(db, user.id, project_id, image_id)
        ann = await AnnotationRepository.find_one_or_none(db, id=ann_id, image_id=image_id)
        if not ann:
            raise HTTPException(status_code=404, detail="Аннотация не найдена")
            
        if update_data.get('class_name'):
            name_to_ru = await cls._resolve_class_names_to_ru(db, project_id, [update_data['class_name']])
            update_data['class_name'] = name_to_ru[update_data['class_name']]
            
        for key, value in update_data.items():
            if value is not None:
                setattr(ann, key, value)
                
        await db.flush()
        return ann

    @classmethod
    async def update_batch(cls, db, user: User, project_id, image_id, updates: List[AnnotationBatchUpdate]) -> List[Annotation]:
        await cls._verify_access(db, user.id, project_id, image_id)
        ann_ids = [u.id for u in updates]
        existing_anns = await AnnotationRepository.find_many_by_ids_and_image(db, ann_ids, image_id)
        existing_map = {str(a.id): a for a in existing_anns}
        
        missing = [str(u.id) for u in updates if str(u.id) not in existing_map]
        if missing:
            raise HTTPException(status_code=404, detail=f"Аннотации не найдены: {missing}")
            
        classes_to_check = [u.class_name for u in updates if u.class_name]
        name_to_ru = await cls._resolve_class_names_to_ru(db, project_id, classes_to_check) if classes_to_check else {}
        
        for u in updates:
            ann = existing_map[str(u.id)]
            update_data = u.model_dump(exclude_unset=True)
            if update_data.get('class_name'):
                update_data['class_name'] = name_to_ru[update_data['class_name']]
            for key, val in update_data.items():
                setattr(ann, key, val)
                
        await db.flush()
        return list(existing_map.values())

    @classmethod
    async def delete_single(cls, db, user: User, project_id, image_id, ann_id) -> dict:
        await cls._verify_access(db, user.id, project_id, image_id)
        ann = await AnnotationRepository.find_one_or_none(db, id=ann_id, image_id=image_id)
        if not ann:
            raise HTTPException(status_code=404, detail="Аннотация не найдена или не принадлежит изображению")
            
        deleted = await AnnotationRepository.delete_by_ids(db, [ann_id])
        return {"status": "success", "deleted_count": deleted}

    @classmethod
    async def delete_batch(cls, db, user: User, project_id, image_id, ann_ids: List) -> dict:
        await cls._verify_access(db, user.id, project_id, image_id)
        deleted_count = await AnnotationRepository.delete_by_ids_and_image(db, ann_ids, image_id)
        return {"status": "success", "deleted_count": deleted_count}


class AnnotationAnalyzeService:
    @staticmethod
    async def _resolve_class_names_to_ru(db, project_id: UUID, class_names: List[str]) -> Dict[str, str]:
        """
        Валидирует классы и возвращает маппинг {входное_имя: name_ru}.
        Поддерживает фоллбэк: если точного совпадения нет, разбивает имя по пробелам 
        и берёт ПЕРВОЕ слово, которое существует в проекте.
        """
        if not class_names:
            return {}
            
        unique_names = list(set(class_names))
        existing = await ClassTypeRepository.find_existing_by_names(db, project_id, unique_names)
        
        exact_map = {}
        for ct in existing:
            exact_map[ct.name_ru] = ct.name_ru
            exact_map[ct.name_eng] = ct.name_ru
            
        resolved_map = {}
        unresolved = []
        
        for name in unique_names:
            if name in exact_map:
                resolved_map[name] = exact_map[name]
                continue
                
            found = False
            for part in name.split():
                part = str(part).strip()
                if part and part in exact_map:
                    resolved_map[name] = exact_map[part]
                    found = True
                    break
                    
            if not found:
                unresolved.append(name)
                
        if unresolved:
            raise HTTPException(status_code=400, detail=f"Классы (или их части) не найдены в проекте: {unresolved}")
        return resolved_map

    @staticmethod
    async def save_detection_annotations(
        db: AsyncSession,
        image_id: UUID,
        result: Dict[str, Any],
    ) -> List[Annotation]:
        """
        Сохраняет аннотации детекции (bounding boxes).
        
        :param result: dict с ключами ['xyxy', 'class', 'confidence']
        :return: список созданных аннотаций
        """
        project_id = await ImageRepository.get_project_id_by_image_id(db, image_id)
        if not project_id:
            raise HTTPException(status_code=404, detail="Изображение не найдено")
        
        xyxy = result.get('xyxy', [])
        classes = result.get('class', [])
        
        unique_classes = [str(c) for c in classes if c is not None and str(c).strip()]
        if not unique_classes:
            return []
        name_to_ru = await AnnotationService._resolve_class_names_to_ru(db, project_id, unique_classes)
        annotations = []
        for i, bbox in enumerate(xyxy):
            # Валидация данных
            if i >= len(classes) or len(bbox) != 4:
                continue
            
            en_class = str(classes[i])
            ru_class = name_to_ru[en_class]

            annotation = Annotation(
                image_id=image_id,
                type=AnnotationType.detection,
                class_name=ru_class,
                data=[float(x) for x in bbox],
                is_selected=False,
            )
            annotations.append(annotation)
        
        if annotations:
            return await AnnotationRepository.create_many(db, annotations)
        return []
    
    @classmethod
    async def save_segmentation_annotations(
        cls,
        db: AsyncSession,
        image_id: UUID,
        result: Dict[str, Any],
        handle_mask_service: HandleMaskService,
        minio_service = minio_service,
    ) -> Tuple[List[Annotation], List[Mask]]:
        """
        Сохраняет аннотации сегментации (маски + полигоны).
        Работает только с масками из result['mask_path'].
        
        :param result: dict с ключом 'mask_path' -> [{'class': ..., 'mask_path': ...}, ...]
        :return: кортеж (список аннотаций, список масок)
        """
        project_id = await ImageRepository.get_project_id_by_image_id(db, image_id)
        if not project_id:
            raise HTTPException(status_code=404, detail="Изображение не найдено")
        
        mask_paths = result.get('mask_path', [])
        
        # class_name → mask_path (первое вхождение)
        mask_path_map: Dict[str, str] = {}
        for mp in (mask_paths or []):
            cls_name = mp.get('class')
            path = mp.get('mask_path')
            if cls_name and path and cls_name not in mask_path_map:
                mask_path_map[cls_name] = path
        
        if not mask_path_map:
            return [], []
            
        # Маппинг английских названий на русские
        name_to_ru = await cls._resolve_class_names_to_ru(db, project_id, list(mask_path_map.keys()))
        
        annotations = []
        masks = []
        
        for en_class, mask_file_path in mask_path_map.items():
            ru_class = name_to_ru.get(en_class)
            if not ru_class:
                logger.warning(f"Class '{en_class}' not found in project mapping, skipping mask.")
                continue
                
            try:
                # Скачиваем маску из MinIO
                mask_bytes = await asyncio.to_thread(
                    minio_service.download_image,
                    filename=mask_file_path,
                    main_path=''
                )
                
                if not mask_bytes:
                    continue
                    
                # Конвертируем в numpy array
                mask_image = np.array(PilImage.open(io.BytesIO(mask_bytes)))
                
                # Получаем полигоны через HandleMaskService
                polygons = handle_mask_service.process_mask(mask_image)
                if not polygons:
                    continue
                
                # Безопасно получаем относительный путь
                try:
                    rel_path = Path(mask_file_path).relative_to(settings.MINIO.OUTPUT_PREFIX)
                except ValueError:
                    # Если префикс не совпадает, берём только имя файла
                    rel_path = Path(mask_file_path).name
                    
                # Создаём путь для сохранения маски
                new_path_mask = minio_service.generate_result_path(
                    original_path=str(rel_path), 
                    suffix="",
                    main_path=settings.MINIO.INPUT_SEGMENTATION_PREFIX,
                )
                
                # Загружаем обратно в MinIO и получаем финальный путь
                file_path = minio_service.upload_image(object_path=new_path_mask, image_bytes=mask_bytes)
                
                # Создаём запись маски (файл)
                mask_obj = Mask(
                    image_id=image_id,
                    file_path=file_path,
                    class_name=ru_class,
                    width=int(mask_image.shape[1]) if len(mask_image.shape) > 1 else None,
                    height=int(mask_image.shape[0]) if len(mask_image.shape) > 1 else None,
                    format='png',
                )
                masks.append(mask_obj)
                
                # Создаём аннотации (по одной на каждый полигон)
                for polygon in polygons:
                    annotations.append(Annotation(
                        image_id=image_id,
                        type=AnnotationType.segmentation,
                        class_name=ru_class,
                        data=polygon,
                        is_selected=False,
                    ))
                    
            except Exception as e:
                logger.warning(f"Failed to process mask for class '{en_class}': {e}")
                continue
        
        # Сохраняем в БД
        if annotations:
            await AnnotationRepository.create_many(db, annotations)
        if masks:
            await MaskRepository.create_many(db, masks)
        
        return annotations, masks