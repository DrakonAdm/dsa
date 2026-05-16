from fastapi import APIRouter, Depends, status, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from server.core.dependencies import get_database
from server.service.application.user.auth_user import AuthUserService
from server.log.logger import Logger
from server.service.transport.user_transport import UserCreate, UserLogin, ChangePassword

router = APIRouter(prefix='/api/auth', tags=['Auth'])

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


def get_auth_service() -> AuthUserService:
    return AuthUserService(logger=Logger().class_log("AuthUserService"))


@router.post("/register/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register_user(
    user_register: UserCreate, 
    db: AsyncSession = Depends(get_database),
    auth_service: AuthUserService = Depends(get_auth_service)
):
    """Регистрация нового пользователя"""
    return await auth_service.register(user_register=user_register, db=db)


@router.post("/login/")
@limiter.limit("5/minute")
async def login_user(
    request: Request,
    response: Response, 
    form_data: UserLogin,
    db: AsyncSession = Depends(get_database),
    auth_service: AuthUserService = Depends(get_auth_service)
):
    """Аутентификация пользователя"""
    return await auth_service.login(
        response=response,
        form_data=form_data,
        request=request,
        db=db
    )


@router.put("/change/", response_model=dict)
async def change_password(
    new_data: ChangePassword,
    db: AsyncSession = Depends(get_database),
    auth_service: AuthUserService = Depends(get_auth_service)
):
    """Смена пароля"""
    return await auth_service.change_password_user(new_data=new_data, db=db)


@router.put("/refresh/")
async def refresh_tokens(    
    response: Response, 
    request: Request, 
    db: AsyncSession = Depends(get_database),
    auth_service: AuthUserService = Depends(get_auth_service)                         
):
    """Обновление токенов"""
    return await auth_service.refresh(response=response, request=request, db=db)


@router.post("/logout/", response_model=dict)
async def logout_user(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_database),
    auth_service: AuthUserService = Depends(get_auth_service)
):
    """Выход из системы"""
    return await auth_service.logout(response=response, request=request, db=db)