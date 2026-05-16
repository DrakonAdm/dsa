from jose import jwt
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import Request, Response, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import delete, select

from server.log.logger import Logger
from server.core.config import settings
from server.service.db.shemas.models import User, RefreshToken
from server.service.dal.repositories.user_repository import UserRepository, RefreshTokenRepository
from server.service.transport.user_transport import UserCreate, UserInDB, ChangePassword, UserLogin, verify_password, hash_token, verify_token
from server.core.dependencies import cheack_password, validate_token, is_too_similar, get_auth_data


class AuthUserService:
    def __init__(self, logger: Logger):
        self.logger = logger.class_log(self.__class__.__name__)

    async def register(
            self, 
            user_register: UserCreate, 
            db: AsyncSession
    ) -> dict:
        
        if not cheack_password(user_register.password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail='Пароль не соответствует условиям безопасности'
            )
         
        user = await UserRepository.find_one_or_none(db, login=user_register.login)
        if user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Пользователь уже существует'
            )
        user = await UserRepository.find_one_or_none(db, email=user_register.email)
        if user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Пользователь уже существует'
            )
        
        user = UserInDB.create_from_password(login=user_register.login, email=user_register.email, password=user_register.password)
        UserRepository.create(
            db=db,
            login=user.login,
            email=user.email,
            hashed_password=user.hashed_password,
        )

        # await db.commit()

        self.logger.get_info(f"Пользователь {user.login} зарегистрирован")
        return {'message': 'Вы успешно зарегистрированы!'}

    async def login(
            self, 
            response: Response,
            form_data: UserLogin,
            request: Request,
            db: AsyncSession
    ):
        
        auth_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

        user = await UserRepository.find_one_or_none(db, login=form_data.login)
        if not user:
            raise auth_error

        # Проверяем блокировку
        if self._is_blocked(user=user):
            self.logger.get_info(f"Пользователь {user.login} заблокирован")
            remaining_time = (user.last_failed_login + timedelta(minutes=settings.USER.BLOCK_TIME_MINUTES)) - datetime.now(timezone.utc)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "account_locked",
                    "message": "Слишком много попыток входа. Попробуйте позднее",
                    "retry_after": int(remaining_time.total_seconds())
                })

        try:
            if not verify_password(form_data.password, user.hashed_password):
                # Увеличиваем счетчик неудачных попыток
                await self._increment_failed_attempts(
                    db=db,
                    user=user,
                )

                self.logger.get_debug(f"Неверный пароль пользователя. Попытка {user.failed_login_attempts} из {settings.USER.MAX_LOGIN_ATTEMPTS}")
                remaining_attempts = settings.USER.MAX_LOGIN_ATTEMPTS - user.failed_login_attempts
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "invalid_credentials",
                        "message": f"Неверное имя пользователя или пароль. Осталось попыток: {remaining_attempts}",
                        "remaining_attempts": remaining_attempts
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except (ValueError, TypeError) as e:
            self.logger.get_debug(f"Ошибка обработки пароля: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервера при проверке пароля"
            )
        
        # Если пароль верный, сбрасываем счетчик неудачных попыток
        await self._reset_login_attempts(
            db=db,
            user=user
        )
        
        if self._is_password_expired(user=user):
            access_token = self._create_access_token({
            "sub": str(user.id), 
            "def": str(user.definition_id) if user.definition_id else None
            })
            # response.set_cookie( key="users_access_token", 
            #                     value=access_token, 
            #                     httponly=True, 
            #                     secure=True, 
            #                     samesite='lax', 
            #                     path="/api"
            #                     )
        
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                "error": "password_expired",
                "message": "Ваш пароль устарел. Пожалуйста, смените его.",
                "redirect_to": "/change-password"
            })

        access_token = self._create_access_token({
            "sub": str(user.id), 
            "def": str(user.definition_id) if user.definition_id else None
            })
        refresh_token = self._create_refresh_token({"sub": str(user.id)})

        # Сохраняем refresh-токен (старый автоматически заменяется)
        await self._save_refresh_token(
            user.id, 
            refresh_token, 
            request, 
            db
            )

        response.set_cookie(
            key="users_access_token", 
            value=access_token, 
            httponly=True, 
            secure=True, 
            samesite='lax', 
            path="/api")
        response.set_cookie(
            key="users_refresh_token", 
            value=refresh_token, 
            httponly=True, 
            secure=True, 
            samesite='lax', 
            path="/api")

        return {
            'access_token': access_token, 
            'refresh_token': refresh_token,
            'token_type': 'bearer'
        }
    
    async def change_password_user(
            self, 
            new_data: ChangePassword,
            db: AsyncSession
    ):
        if not cheack_password(new_data.password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail='Пароль не соответствует условиям безопасности'
            )

        try:
            user = await UserRepository.find_one_or_none(db, login=new_data.login)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Неверное имя пользователя или пароль",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except Exception:
            raise
        
        try:
            if not verify_password(new_data.old_password, user.hashed_password):
                self.logger.get_debug(f"Неверный пароль пользователя")
                raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный старый пароль"
            )

            if is_too_similar(new_data.old_password, new_data.password):
                self.logger.get_debug(f"Пароли слабо различаются")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Новый пароль слишком похож на старый"
                )
        except (ValueError, TypeError):
            self.logger.get_debug(f"Ошибка обработки")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный тип токена"
            )
        
        if verify_password(new_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Новый пароль не должен совпадать со старым"
            )
        
        await self._change_password(user, new_data.get_password_hash(new_data.password), db)

        self.logger.get_info(f"Пользователь {user.login} сменил пароль")
        return {'message': 'Вы успешно сменили пароль!'}
    
    @staticmethod
    async def _change_password(user: User, hash_password: str, db: AsyncSession):
        user.hashed_password = hash_password
        user.time_created_password = datetime.now(timezone.utc)  # Обновляем время
        # await db.commit()

    @staticmethod
    def _is_password_expired(user: User) -> bool:
        """Проверяет, истёк ли срок действия пароля."""
        expiry_date = user.time_created_password + timedelta(days=settings.USER.TIME_LIVE_PASSWORD)
        return datetime.now(timezone.utc) > expiry_date

    @staticmethod
    async def _reset_login_attempts(db: AsyncSession, user: User):
        user.failed_login_attempts = 0
        user.last_failed_login = None
        # await db.commit()

    @staticmethod
    async def _increment_failed_attempts(db: AsyncSession, user: User):
        if user.failed_login_attempts >= 5:
            user.failed_login_attempts = 0
        user.failed_login_attempts += 1
        user.last_failed_login = datetime.now(timezone.utc)
        # await db.commit()

    @staticmethod
    def _is_blocked(user: User) -> bool:
        if not user.last_failed_login or user.failed_login_attempts < settings.USER.MAX_LOGIN_ATTEMPTS:
            return False
        block_time = user.last_failed_login + timedelta(minutes=settings.USER.BLOCK_TIME_MINUTES)
        return datetime.now(timezone.utc) < block_time

    async def refresh(
            self, 
            response: Response, 
            request: Request, 
            db: AsyncSession
    ):
        try:
            refresh_token = self._get_refresh_token(request)
            payload = await validate_token(refresh_token)
            
            user_id_str = payload.get("sub")
            if not user_id_str:
                self.logger.get_debug(f"Пусто для преобразования строки")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Неверный тип токена')

            """Поиск токена в бд"""
            db_token = await db.execute(
                select(RefreshToken).where(RefreshToken.user_id == UUID(user_id_str)))
            db_token = db_token.scalar_one_or_none()
            
            if not db_token or not verify_token(refresh_token, db_token.token):
                self.logger.get_debug(f"Не найден refresh токен пользователя")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный тип токена")

            user = await UserRepository.find_one_or_none(db, id=UUID(user_id_str))
            if not user:
                self.logger.get_debug(f"Не найден Пользователь")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Неверный тип токена')

            new_access_token = self._create_access_token({
                "sub": str(user.id), 
                "def": str(user.definition_id) if user.definition_id else None
            })
            new_refresh_token = self._create_refresh_token({"sub": str(user.id)})

            # Обновляем refresh-токен в БД
            await self._save_refresh_token(user.id, new_refresh_token, request, db)

            response.set_cookie(
                key="users_access_token", 
                value=new_access_token, 
                httponly=True, secure=True, 
                samesite='lax', 
                path="/api"
            )
            response.set_cookie(
                key="users_refresh_token", 
                value=new_refresh_token, 
                httponly=True, 
                secure=True, 
                samesite='lax', 
                path="/api"
            )

            return {
                'access_token': new_access_token,
                'refresh_token': new_refresh_token,
                'token_type': 'bearer'
            }
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Не удалось обновить токены"
            )
        
    async def logout(self, 
                      response: Response, 
                      request: Request, 
                      db: AsyncSession
                      ):
        try:
            refresh_token = self._get_refresh_token(request)
            payload = await validate_token(refresh_token)
                
            user_id_str = payload.get("sub")
            if user_id_str:
                # Удаляем все refresh токены пользователя из БД
                await RefreshTokenRepository.delete_by_user_id(
                    db=db, 
                    user_id=UUID(user_id_str),
                )
                # await db.commit()
                self.logger.get_info(f"Удалили токен из бд пользователя {user_id_str}")
                
            # Удаляем cookies
            response.delete_cookie(key="users_access_token")
            response.delete_cookie(key="users_refresh_token")

            return {'message': 'Вы успешно разлогинились!'}
        except Exception as e:
            self.logger.get_error(f"Ошибка разлогирования {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Не удалось обновить токены"
            )
        
    def _create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        to_encode.update({
            "exp": expire,
            "type": settings.TOKEN.ACCESS_TYPE, 
            "iss": settings.TOKEN.ISSUER,
            "aud": settings.TOKEN.AUDIENCE,
        })
        auth_data = get_auth_data()

        try:
            encode_jwt = jwt.encode(to_encode, auth_data['secret_key'], algorithm=auth_data['algorithm'])
        except (TypeError, ValueError) as e:
            self.logger.get_debug(f"Ошибка создания acces токена {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Токен не создан"
            )
        return encode_jwt

    def _create_refresh_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=30)
        to_encode.update({
            "exp": expire,
            "type": settings.TOKEN.ACCESS_TYPE,
            "iss": settings.TOKEN.ISSUER,
            "aud": settings.TOKEN.AUDIENCE,
            "iat": datetime.now(timezone.utc).timestamp()
        })
        auth_data = get_auth_data()

        try:
            encode_jwt = jwt.encode(to_encode, auth_data['secret_key'], algorithm=auth_data['algorithm'])
        except (TypeError, ValueError) as e:
            self.logger.get_debug(f"Ошибка создания refresh токена {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Токен не создан"
            )
        return encode_jwt
    
    # async def _save_refresh_token(self, user_id: UUID, token: str, request: Request, db: AsyncSession):
    #     # Удаляем старый токен (если есть) и сохраняем новый
    #     await RefreshTokenRepository.delete_by_user_id(
    #         db=db,
    #         user_id=user_id,
    #     )
    #     RefreshTokenRepository.create(
    #         db=db,
    #         user_id=user_id,
    #         token=hash_token(token),
    #         expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    #         user_agent=request.headers.get("User-Agent"),
    #         ip_address=request.client.host if request.client else None,
    #     )
        # await db.commit()

    async def _save_refresh_token(self, user_id: UUID, token: str, request: Request, db: AsyncSession):
        stmt = insert(RefreshToken).values(
            user_id=user_id,
            token=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        ).on_conflict_do_update(
            index_elements=['user_id'],
            set_=dict(
                token=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                user_agent=request.headers.get("User-Agent"),
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.execute(stmt)
        
    def _get_refresh_token(self, request: Request):
        token = request.cookies.get('users_refresh_token')
        if not token:
            self.logger.get_debug(f"Не найден refresh токен")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Не найден refresh токен')
        return token
    