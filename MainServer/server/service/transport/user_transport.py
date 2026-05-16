from typing import Optional
from pydantic import BaseModel, Field, field_validator
from uuid import UUID, uuid4
from passlib.context import CryptContext

# Настройка хеширования паролей
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class UserBase(BaseModel):
    login: str = Field(default=..., min_length=1, max_length=50, description="Логин пользователя")

class UserDefinitionBase(BaseModel):
    name_company: Optional[str] = Field(default=None, max_length=500, description="Группа пользователя")
    definition: Optional[str] = Field(default=None, max_length=500, description="Какое-то доп. описание")

    @field_validator("name_company", "definition", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

class UserCreate(BaseModel):
    email: str = Field(default=..., min_length=1, max_length=100, description="Email пользователя")
    login: str = Field(default=..., min_length=1, max_length=100, description="Логин пользователя")
    password: str  # Пароль в открытом виде (только при создании)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

class UserLogin(UserCreate):
    email: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Email пользователя (необязательно для смены пароля)"
    )

class ChangePassword(UserCreate):
    email: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Email пользователя (необязательно для смены пароля)"
    )
    old_password: str

class UserInDB(UserBase):
    login: str = Field(default=..., min_length=1, max_length=100, description="Логин пользователя")
    email: str = Field(default=..., min_length=1, max_length=100, description="Логин пользователя")
    hashed_password: str  # Пароль хранится только в хешированном виде

    @classmethod
    def create_from_password(cls, login: str, email: str, password: str, **kwargs):
        """Создает пользователя с хешированным паролем."""
        hashed_password = pwd_context.hash(password)
        return cls(login=login, email=email, hashed_password=hashed_password, **kwargs)

class UserPublic(UserBase):
    id: UUID = Field(default_factory=uuid4, description="ID пользователя")

def verify_password(password, hashed_password: str) -> bool:
        """Проверяет, совпадает ли пароль с хешем."""
        return pwd_context.verify(password, hashed_password)

def hash_token(token: str) -> str:
    """Хеширует refresh-токен перед сохранением в БД"""
    return pwd_context.hash(token)

def verify_token(plain_token: str, hashed_token: str) -> bool:
    """Проверяет соответствие refresh-токена его хешу"""
    return pwd_context.verify(plain_token, hashed_token)