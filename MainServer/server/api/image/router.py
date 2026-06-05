import json
import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query,  HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Any
from uuid import UUID

from server.core.dependencies import get_database, get_token, search_check_user
from server.service.transport.request.request import ListImageLoadRequest, ImageUploadRequest
from server.service.transport.response.response import ImageResponse
from server.service.application.image_service import ImageService

router = APIRouter(prefix='/api/image', tags=['Image'])


@router.post("/{project_id}/images/upload", response_model=List[ImageResponse])
async def upload_images_endpoint(
    project_id: str,
    files: List[UploadFile] = File(..., description="Файлы изображений"),
    metadata_json: Optional[str] = Form(None, description="JSON список метаданных изображений"),
    mask_files: Optional[List[UploadFile]] = File(None, description="Файлы масок (опционально, порядок соответствует маскам в метаданных)"),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    normalized_mask_files = [file for file in (mask_files or []) if file.filename]

    if metadata_json and metadata_json.strip():
        try:
            raw_metadata = json.loads(metadata_json)
            if not isinstance(raw_metadata, list):
                raise ValueError("metadata must be a list")
            metadata = [ImageUploadRequest(**m) for m in raw_metadata]
        except Exception:
            raise HTTPException(status_code=400, detail="Неверный формат JSON в поле metadata")
    else:
        if normalized_mask_files:
            raise HTTPException(status_code=400, detail="Для загрузки масок необходимо передать metadata_json")
        metadata = [ImageUploadRequest() for _ in files]
        
    if len(files) != len(metadata):
        raise HTTPException(status_code=400, detail="Количество файлов изображений не соответствует количеству метаданных")

    return await ImageService.upload_images(db, user, project_id, metadata, files, normalized_mask_files, logger)


@router.get("/{project_id}/images", response_model=List[ImageResponse])
async def get_project_images_endpoint(
    project_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    images = await ImageService.get_project_images(db, user, project_id, logger)
    
    return [ImageResponse.model_validate(img, from_attributes=True) for img in images]


@router.get("/{project_id}/images/download")
async def download_multiple_images(
    project_id: UUID,
    image_ids: List[UUID] = Query(..., min_length=1, max_length=50),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    
    generator, content_type, filename = await ImageService.stream_zip_from_minio(
        db, user, project_id, image_ids, logger
    )
    
    return StreamingResponse(
        generator,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/{project_id}/images/{image_id}/download")
async def download_single_image(
    project_id: UUID,
    image_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    
    generator, content_type, filename = await ImageService.stream_minio_file(
        db, user, project_id, image_id, logger
    )
    
    return StreamingResponse(
        generator,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.delete("/{project_id}/images/{image_id}", response_model=dict)
async def delete_image_endpoint(
    project_id: str,
    image_id: str,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    return await ImageService.soft_delete_image(db, user, project_id, image_id, logger)