from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse
from fastapi import Request
from server.service.dal.repositories import CacheObjectClassesRepository
import logging

from server.core.config import settings

logger = logging.getLogger("InternalAuth")


class InternalServiceAuth:
    """
    Сервис проверки запросов от внутренних микросервисов.
    Использует кэш ModelConfig для валидации источника запроса.
    """
    
    ALLOWED_CALLBACK_PATHS = frozenset(['/api/analyze/analysis'])
    
    def __init__(self):
        self._allowed_hosts: set[str] = set()
        self._allowed_ips: set[str] = set()
        self._cache_ready: bool = False
    
    async def refresh_from_cache(self, db: AsyncSession) -> None:
        """
        Обновляет списки разрешённых хостов и IP из кэша.
        Вызывать при старте приложения и при инвалидации кэша.
        """
        try:
            configs = await CacheObjectClassesRepository.get_base_classes(db)
            
            new_hosts = set()
            new_ips = set()
            
            for cfg in configs:
                if not cfg.is_active or not cfg.endpoint_url:
                    continue
                    
                parsed = urlparse(cfg.endpoint_url)
                hostname = parsed.hostname
                
                if not hostname:
                    continue
                
                # Если hostname выглядит как IP — добавляем в allowed_ips
                if self._is_ip_address(hostname):
                    new_ips.add(hostname)
                else:
                    new_hosts.add(hostname)
            
            self._allowed_hosts = new_hosts
            self._allowed_ips = new_ips
            self._cache_ready = True
            
            logger.info(
                f"Internal auth cache refreshed: {len(new_hosts)} hosts, {len(new_ips)} IPs"
            )
            
        except Exception as e:
            logger.error(f"Failed to refresh internal auth cache: {e}")
            # Не сбрасывает _cache_ready, чтобы не блокировать все запросы
            # Старые значения останутся в силе до следующего успешного обновления
    
    @staticmethod
    def _is_ip_address(hostname: str) -> bool:
        """Проверяет, является ли строка IP-адресом."""
        import ipaddress
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False
    
    def is_request_allowed(self, request: Request) -> bool:
        """
        Проверяет, разрешён ли запрос от внутреннего сервиса.
        """
        # Проверка пути
        if request.url.path not in self.ALLOWED_CALLBACK_PATHS:
            return False
        
        # Если кэш ещё не загружен — отказываем в доступе (fail-secure)
        if not self._cache_ready:
            logger.warning(f"Auth cache not ready, denying request to {request.url.path}")
            return False
        
        # Получаем клиентский хост (с учётом прокси)
        client_host = self._get_client_host(request)
        
        # Проверка по разрешённым хостам
        if client_host in self._allowed_hosts or client_host in self._allowed_ips:
            return True
        
        """Удалить !!!"""
        # if client_host == '127.0.0.1':
        #     return True
        
        # проверка по заголовку Referer/Origin (если микросервис его шлёт)
        referer = request.headers.get("referer") or request.headers.get("origin")
        if referer:
            referer_host = urlparse(referer).hostname
            if referer_host and (referer_host in self._allowed_hosts or referer_host in self._allowed_ips):
                return True
        
        # проверка по кастомному заголовку (двухфакторная аутентификация)
        internal_token = request.headers.get("X-Internal-Service-Token")
        if internal_token and internal_token == settings.INTERNAL_SERVICE_TOKEN:
            return True
        
        return False
    
    @staticmethod
    def _get_client_host(request: Request) -> str:
        """
        Извлекает реальный клиентский хост с учётом прокси-заголовков.
        """
        # X-Forwarded-For > X-Real-IP > прямой client.host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # X-Forwarded-For может содержать цепочку: "client, proxy1, proxy2"
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        
        return request.client.host if request.client else ""
    
    def get_allowed_endpoints_info(self) -> dict:
        """
        Возвращает информацию о разрешённых эндпоинтах для отладки/мониторинга.
        """
        return {
            "paths": list(self.ALLOWED_CALLBACK_PATHS),
            "hosts": list(self._allowed_hosts),
            "ips": list(self._allowed_ips),
            "cache_ready": self._cache_ready
        }

internal_auth_service = InternalServiceAuth()