from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.core.dependencies import get_database, get_token
from server.service.application.user.data_user import DataBaseDataUserService
from server.log.logger import Logger
from server.service.transport.user_transport import UserBase, UserDefinitionBase


router = APIRouter(prefix='/api/user', tags=['DataUser'])


@router.get("/me/", response_model=UserBase)
async def get_me(
    token: str = Depends(get_token), 
    db: AsyncSession = Depends(get_database)
):
    """Получение данных текущего пользователя"""
    return await DataBaseDataUserService.get_current_user(
        logger=Logger().class_log("UserRouter"), 
        token=token, 
        db=db
    )


@router.get("/about/me", response_model=UserDefinitionBase)
async def get_definition_me(
    token: str = Depends(get_token), 
    db: AsyncSession = Depends(get_database)
):
    """Получение расширенных данных пользователя"""
    return await DataBaseDataUserService.get_current_definition_user(
        logger=Logger().class_log("UserRouter"), 
        token=token, 
        db=db
    )


@router.put("/change/login", response_model=UserBase)
async def change_login(
    new_login: UserBase,
    token: str = Depends(get_token), 
    db: AsyncSession = Depends(get_database)
):
    """Смена логина (временно отключено)"""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Ссылка временно недоступна"
    )


@router.put("/change/definition", response_model=UserDefinitionBase)
async def change_definition(
    new_def: UserDefinitionBase,
    token: str = Depends(get_token), 
    db: AsyncSession = Depends(get_database)
):
    """Обновление расширенных данных пользователя"""
    return await DataBaseDataUserService.change_definition_user(
        logger=Logger().class_log("UserRouter"), 
        new_definition=new_def, 
        token=token, 
        db=db
    )