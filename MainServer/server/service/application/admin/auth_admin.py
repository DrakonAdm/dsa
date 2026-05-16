import os
from fastapi import Request
from sqladmin.authentication import AuthenticationBackend
from passlib.context import CryptContext

from server.core.config import settings

# Настройка хеширования паролей
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]
        
        # Получаем сохранённые учётные данные
        admin_username = settings.ADMIN.ADMIN_USERNAME
        admin_username2 = settings.ADMIN.ADMIN_USERNAME2
        hashed_password = settings.ADMIN.ADMIN_HASHED_PASSWORD
        hashed_password2 = settings.ADMIN.ADMIN_HASHED_PASSWORD2
        
        # Проверяем наличие учётных данных
        if not all([admin_username, admin_username2, hashed_password, hashed_password2]):
            return False
            
        # Проверяем соответствие username и password
        if username == admin_username and pwd_context.verify(password, hashed_password):
            request.session.update({
                "token": "your_generated_token_here", 
                "username": username
            })
            return True
            
        if username == admin_username2 and pwd_context.verify(password, hashed_password2):
            request.session.update({
                "token": "your_generated_token_here",
                "username": username
            })
            return True
            
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        username = request.session.get("username")
        
        if not token or not username:
            return False
            
        # Проверяем, что username соответствует одному из разрешённых
        admin_username = settings.ADMIN.ADMIN_USERNAME
        admin_username1 = settings.ADMIN.ADMIN_USERNAME2
        
        return username in (admin_username, admin_username1)
    