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
    metadata: str = Form(
        ...,
        description="JSON строка с метаданными изображений"
    ),
    files: List[UploadFile] = File(
        ...,
        description="Файлы изображений"
    ),
    mask_files: Any = File(
        default=None,
        description="Файлы масок"
    ),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ImageRouter")
    user = await search_check_user(token, logger, db)
    
    try:
        metadata_obj = ListImageLoadRequest.model_validate_json(metadata)
        metadata_list = metadata_obj.metadata or []
    except Exception as e:
        # raise HTTPException(status_code=422, detail=f"Ошибка валидации metadata: {str(e)}")
        metadata_list = []

    try:
        if mask_files is None:
            mask_files = []

        elif not isinstance(mask_files, list):
            mask_files = [mask_files]

        mask_files = [
            f for f in mask_files
            if isinstance(f, UploadFile)
        ]
    except Exception as e:
        mask_files = []

    if len(metadata_list) < len(files):
        metadata_list.extend([ImageUploadRequest() for _ in range(len(files) - len(metadata_list))])
    elif len(metadata_list) > len(files):
        metadata_list = metadata_list[:len(files)]

    mask_files = mask_files or []

    return await ImageService.upload_images(
        db=db,
        user=user,
        project_id=project_id,
        metadata=metadata_list,
        files=files,
        mask_files=mask_files,
        logger=logger
    )


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