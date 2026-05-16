from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging

from server.core.config import settings
from server.core.dependencies import get_token, validate_token
from server.core.internal_auth import internal_auth_service

logger = logging.getLogger(__name__)

# Пути, исключаемые из проверки авторизации
EXCLUDED_AUTH_PATHS = frozenset([
    '/api/auth/login',
    '/api/auth/register', 
    '/api/auth/refresh',
    '/api/auth/change',
    '/docs',
    '/openapi.json',
    '/redoc',
])

async def auth_middleware(request: Request, call_next):
    """
    Middleware для проверки JWT-токена на /api/* эндпоинтах
    + проверка внутренних сервисов через InternalServiceAuth.
    """
    # Пропускаем исключённые пути (логин, доки и т.д.)
    if any(request.url.path.startswith(path) for path in EXCLUDED_AUTH_PATHS):
        return await call_next(request)
    
    # Проверяем только API-маршруты
    if request.url.path.startswith('/api/'):
        if internal_auth_service.is_request_allowed(request):
            return await call_next(request)
        try:
            token = get_token(request)
            await validate_token(token)
        except HTTPException as e:
            logger.debug(
                f"Auth failed for {request.url.path} from {request.client.host}: {e.detail}"
            )
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
                headers=e.headers if hasattr(e, "headers") else None
            )
    
    return await call_next(request)


async def ip_whitelist_middleware(request: Request, call_next):
    """
    Middleware для фильтрации по разрешённым IP.
    Если settings.ALLOWED.IPS пуст — проверка отключена.
    """
    if settings.ALLOWED.IPS:
        client_ip = request.client.host if request.client else None
        # Поддержка прокси
        if x_forwarded := request.headers.get("X-Forwarded-For"):
            client_ip = x_forwarded.split(",")[0].strip()
            
        if client_ip and client_ip not in settings.ALLOWED.IPS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for IP: {client_ip}"
            )
    
    return await call_next(request)


async def logger_middleware(request: Request, call_next, logger):
    """
    Middleware для логирования запросов (опционально).
    """
    logger.get_info(f"{request.method} {request.url.path} from {request.client.host}")
    response = await call_next(request)
    logger.get_info(f"Response {response.status_code} for {request.url.path}")
    return response