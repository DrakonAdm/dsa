import logging
from fastapi import APIRouter, Depends, Query,  HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from server.core.dependencies import get_database, get_token, search_check_user
from server.service.dal.repositories import ProjectRepository, UserRepository
from server.service.transport import ProjectCreate, ClassTypeCreate, AddMemberRequest, ProjectResponse, ProjectsUserResponse, ClassTypeResponse, UserSearchResponse
from server.service.application.project_service import ProjectService
from server.service.transport.base_transport import ModelConfigBase


router = APIRouter(prefix='/api/projects', tags=['Projects'])

@router.post("/", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.create_project(db, user, data, logger)

@router.get("/", response_model=ProjectsUserResponse)
async def get_project_user(
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.get_user_projects(db, user, logger)


@router.delete("/{project_id}", response_model=dict)
async def delete_project(
    project_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.delete_project(db, user, project_id, logger)

@router.get("/{project_id}/models", response_model=List[ModelConfigBase])
async def get_project_models(
    project_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    if not await ProjectRepository.is_user_member(db, user.id, project_id):
        print(f"user.id = {user.id}, project_id = {project_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")
    
    models = await ProjectService.get_available_models(db, logger)
    return models

@router.post("/{project_id}/classes", response_model=ClassTypeResponse)
async def create_class_type(
    project_id: UUID,
    data: ClassTypeCreate,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.create_class_type(db, user, project_id, data, logger)

@router.get("/{project_id}/classes", response_model=List[ClassTypeResponse])
async def get_class_types(
    project_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.get_class_types(db, user, project_id, logger)

@router.delete("/{project_id}/classes/{class_type_id}", response_model=dict)
async def delete_class_type(
    project_id: UUID,
    class_type_id: UUID,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.delete_class_type(db, user, class_type_id, logger)

@router.post("/{project_id}/members", response_model=dict)
async def add_member_to_project(
    project_id: UUID,
    data: AddMemberRequest,
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    return await ProjectService.add_member(db, user, project_id, data, logger)

@router.get("/users/search", response_model=List[UserSearchResponse])
async def search_users(
    q: str = Query(..., min_length=1, max_length=100, description="Поисковый запрос"),
    limit: int = Query(20, ge=1, le=100, description="Лимит результатов"),
    token: str = Depends(get_token),
    db: AsyncSession = Depends(get_database)
):
    logger = logging.getLogger("ProjectRouter")
    user = await search_check_user(token, logger, db)
    
    # Поиск доступен только авторизованным пользователям
    users = await UserRepository.search_users(db, q, limit)
    return [UserSearchResponse.model_validate(u, from_attributes=True) for u in users]