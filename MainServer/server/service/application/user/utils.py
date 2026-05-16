from jose import jwt, JWTError, ExpiredSignatureError
from datetime import datetime, timezone
from uuid import UUID
from fastapi import Request, HTTPException, status
import re
from Levenshtein import distance as levenshtein_distance

from server.core.config import settings
from server.service.db.shemas.models import User, UserDefinition
from server.service.dal.repositories.user_repository import UserDefinitionRepository, UserRepository


def get_auth_data():
    return {"secret_key": settings.ADMIN.AUTH_SECRET, "algorithm": settings.ADMIN.AUTH_ALGORITHM}


def cheack_password(password=None):
    if not password:
        return False
    # Проверяем:
    # - минимум 1 цифру (?=\D*\d)
    # - минимум 1 заглавную букву (?=[^A-Z]*[A-Z])
    # - минимум 1 строчную букву (?=[^a-z]*[a-z])
    # - минимум 1 спецсимвол (?=[^!@#$%^&*()_+{}[\]|:;'"<>,.?/~`-]*[!@#$%^&*()_+{}[\]|:;'"<>,.?/~`-])
    # - разрешённые символы: буквы, цифры и спецсимволы [A-Za-z0-9!@#$%^&*()_+{}[\]|:;'"<>,.?/~`-]
    # - длину от 14 символов {14,}
    rx = re.compile(
        r'^(?=\D*\d)'                          # минимум 1 цифра
        r'(?=[^A-Z]*[A-Z])'                    # минимум 1 заглавная буква
        r'(?=[^a-z]*[a-z])'                    # минимум 1 строчная буква
        r'(?=[^!@#$%^&*()_+{}\[\]|:;\'"<>,.?/~`-]*[!@#$%^&*()_+{}\[\]|:;\'"<>,.?/~`-])'  # минимум 1 спецсимвол
        r'[A-Za-z0-9!@#$%^&*()_+{}\[\]|:;\'"<>,.?/~`-]{14,}$'  # разрешённые символы и длина
    )
    return bool(rx.match(password))

def is_too_similar(old_pass: str, new_pass: str, threshold=0.7) -> bool:
    """Проверяет схожесть паролей с порогом (по умолчанию 70%)"""
    dist = levenshtein_distance(old_pass, new_pass)
    max_len = max(len(old_pass), len(new_pass))
    similarity = 1 - dist/max_len
    return similarity > threshold

def get_token(request: Request):
        token = request.cookies.get('users_access_token')
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Токен истек')
        return token

def cheack_token(
        payload,
        ) -> bool:
    if not payload.get('type') in {settings.TOKEN.ACCESS_TYPE, settings.TOKEN.REFRESH_TYPE}:
        return False
    return True

async def validate_token(token: str):
    try:
        auth_data = get_auth_data()
        payload = jwt.decode(
            token, 
            auth_data['secret_key'], 
            algorithms=auth_data['algorithm'],
            issuer=settings.TOKEN.ISSUER,
            audience=settings.TOKEN.AUDIENCE,
            )
        
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Токен истек')
    except JWTError as e:  # Общее исключение для всех ошибок JWT
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f'Неверный токен: {str(e)}')
    
    if 'exp' not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Токен истек"
            )
    
    expire = payload.get('exp')
    expire_time = datetime.fromtimestamp(int(expire), tz=timezone.utc)
    if (not expire) or (expire_time < datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Токен истек')
    
    if not cheack_token(payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Токен истек')
    
    return payload


async def search_check_user(token, logger, db) -> User:
    try:
        payload = await validate_token(token)
    except Exception:
        raise

    user_id_str = payload.get("sub")
    if not user_id_str:
        logger.get_debug(f"Не найдены данные по пользователю")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Неверный тип токена')
    
    try:
        user_id = UUID(user_id_str)
    except Exception:
        logger.get_debug(f"Неверный формат ID данных пользователя")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Неверный тип токена')
    
    user = await UserRepository.find_one_or_none(db, id=user_id)
    if not user:
        logger.get_debug(f"Не найден пользователь")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Неверный тип токена')
    
    return user

async def get_definition_user(token, logger, db) -> UserDefinition:
    payload = await validate_token(token)

    def_id_str = payload.get("def")
    if not def_id_str:
        logger.get_debug(f"Не найдены данные по пользователю")
        return None
    
    try:
        def_id = UUID(def_id_str)
    except Exception:
        logger.get_debug(f"Неверный формат ID данных пользователя")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Неверный тип токена')
    
    user_def = await UserDefinitionRepository.find_one_or_none(db, id=def_id)
    if not user_def:
        logger.get_debug(f"Не найдены данные по пользователю")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Неверный тип токена')
    
    return user_def
