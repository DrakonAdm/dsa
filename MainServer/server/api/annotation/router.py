import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from server.core.dependencies import get_database, get_token, search_check_user
from server.service.transport import AnnotationResponse, AnnotationCreate, AnnotationUpdate, AnnotationBatchUpdate
from server.service.application.annotation_service import AnnotationService

router = APIRouter(prefix='/api/annotations', tags=['Annotations'])

@router.get("/{project_id}/images/{image_id}", response_model=List[AnnotationResponse])
async def get_annotations(
    project_id: UUID,
    image_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.get_by_image(db, user, project_id, image_id)

@router.post("/{project_id}/images/{image_id}", response_model=AnnotationResponse)
async def create_annotation(
    project_id: UUID,
    image_id: UUID,
    data: AnnotationCreate,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.create(db, user, project_id, image_id, data)

@router.post("/{project_id}/images/{image_id}/batch", response_model=List[AnnotationResponse])
async def create_annotations_batch(
    project_id: UUID,
    image_id: UUID,
    data_list: List[AnnotationCreate],
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.create_batch(db, user, project_id, image_id, data_list)

@router.put("/{project_id}/images/{image_id}/batch", response_model=List[AnnotationResponse])
async def update_annotations_batch(
    project_id: UUID,
    image_id: UUID,
    updates: List[AnnotationBatchUpdate],
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.update_batch(db, user, project_id, image_id, updates)

@router.delete("/{project_id}/images/{image_id}/batch", response_model=dict)
async def delete_annotations_batch(
    project_id: UUID,
    image_id: UUID,
    ann_ids: List[UUID] = Query(..., min_length=1, max_length=100, description="Список UUID аннотаций"),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.delete_batch(db, user, project_id, image_id, ann_ids)

@router.put("/{project_id}/images/{image_id}/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    project_id: UUID,
    image_id: UUID,
    annotation_id: UUID,
    data: AnnotationUpdate,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.update_single(db, user, project_id, image_id, annotation_id, data.model_dump(exclude_unset=True))

@router.delete("/{project_id}/images/{image_id}/{annotation_id}", response_model=dict)
async def delete_annotation(
    project_id: UUID,
    image_id: UUID,
    annotation_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("AnnotationRouter")
    user = await search_check_user(token, logger, db)
    return await AnnotationService.delete_single(db, user, project_id, image_id, annotation_id)
