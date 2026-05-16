from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.orm import column_property
from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Integer, JSON, Table, UniqueConstraint, ARRAY
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base


# Базовый класс для моделей
Base = declarative_base()

# Enums для типизации
class ModelType(str, Enum):
    segmentation = "segmentation"
    detection = "detection"
    sahi_detection = "sahi_detection"
    sahi_segmentation = "sahi_segmentation"

class AnnotationType(str, Enum):
    segmentation = "segmentation"
    detection = "detection"

class UserType(str, Enum):
    serf = "serf"
    premium = "premium"

class ImageType(str, Enum):
    delete = "delete"
    active = "active"

class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    queued = "queued"
    failed = "failed"
    cancelled = "cancelled"

# Ассоциативная таблица Many-to-Many
project_user_table = Table(
    'project_user',
    Base.metadata,
    Column('user_by_id', PG_UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True),
    Column('project_by_id', PG_UUID(as_uuid=True), ForeignKey('projects.id'), primary_key=True)
)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String, nullable=False, unique=True, index=True)
    login = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    definition_id = Column(PG_UUID(as_uuid=True), ForeignKey('user_definitions.id'), nullable=True, unique=True)
    time_created_password = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    type_subscriptions = Column(
        SQLEnum(UserType, name="user_type", create_type=True),
        nullable=False,
        default=UserType.serf
    )

    failed_login_attempts = Column(Integer, default=0, nullable=False)  # Количество неудачных попыток
    last_failed_login = Column(DateTime(timezone=True), nullable=True)  # Время последней неудачной попытки
    
    definition = relationship("UserDefinition", back_populates="user")
    refresh_token = relationship("RefreshToken", back_populates="user", uselist=False)  # Обратная связь
    created_projects = relationship("Project", foreign_keys="Project.created_by_id", back_populates="creator")
    projects = relationship("Project", secondary=project_user_table, back_populates="members")
    oauth_accounts = relationship("OAuthAccount", back_populates="user")
    images = relationship("Image", back_populates="user")

class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_provider_user'),
    )
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    
    provider = Column(String) # "yandex", "google", "vk"
    provider_user_id = Column(String) # ID пользователя внутри провайдера (sub, id)
    
    user = relationship("User", back_populates="oauth_accounts")

class UserDefinition(Base):
    __tablename__ = 'user_definitions'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name_company = Column(String(500), nullable=True)
    definition = Column(String(500), nullable=True)
    
    user = relationship("User", back_populates="definition", uselist=False)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)  # Primary key для гарантии единственности
    token = Column(String(512), unique=True, nullable=False)  # Хешированный токен
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_agent = Column(String(255))
    ip_address = Column(String(45))

    user = relationship("User", back_populates="refresh_token", uselist=False)  # Связь один-к-одному

class Image(Base):
    __tablename__ = 'images'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # Primary key для гарантии единственности
    project_id = Column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # Primary key для гарантии единственности
    file_path = Column(String(500), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    format = Column(String(10), nullable=True)
    type_subscriptions = Column(
        SQLEnum(ImageType, name="image_type", create_type=True),
        nullable=False,
        default=ImageType.active
    )

    project = relationship("Project", back_populates="images")
    user = relationship("User", back_populates="images")
    annotations = relationship("Annotation", back_populates="image", cascade="all, delete-orphan")
    masks = relationship("Mask", back_populates="image", cascade="all, delete-orphan")
    analysis_tasks = relationship("AnalysisTask", back_populates="image", cascade="all, delete-orphan")

class ModelConfig(Base):
    __tablename__ = 'models'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    type = Column(SQLEnum(ModelType), nullable=False)
    endpoint_url = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

class Project(Base):
    __tablename__ = 'projects'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    created_by_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_projects")
    members = relationship("User", secondary=project_user_table, back_populates="projects")
    images = relationship("Image", back_populates="project", cascade="all, delete-orphan")
    class_types = relationship("ClassTypeProject", back_populates="project", cascade="all, delete-orphan")


class ClassTypeProject(Base):
    __tablename__ = 'class_types'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name_ru = Column(String(255), nullable=False)
    name_eng = Column(String(255), nullable=False)
    project_id = Column(PG_UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False)

    project = relationship("Project", back_populates="class_types")
    
    __table_args__ = (
        UniqueConstraint('project_id', 'name_ru', name='uq_project_class_name_ru'),
        UniqueConstraint('project_id', 'name_eng', name='uq_project_class_name_eng'),
    )

class Annotation(Base):
    __tablename__ = 'annotations'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    image_id = Column(PG_UUID(as_uuid=True), ForeignKey('images.id'), nullable=False)
    type = Column(SQLEnum(AnnotationType), nullable=False)
    class_name = Column(String(200), nullable=False) # наименование класса на русском языке
    data = Column(JSON, nullable=False)  # В PostgreSQL автоматически маппится на JSONB
    is_selected = Column(Boolean, default=False, nullable=False)

    image = relationship("Image", back_populates="annotations")

class Mask(Base):
    __tablename__ = 'masks'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    image_id = Column(PG_UUID(as_uuid=True), ForeignKey('images.id'), nullable=False)
    file_path = Column(String(500), nullable=False)
    class_name = Column(String(200), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    format = Column(String(10), nullable=True)

    image = relationship("Image", back_populates="masks")


class AnalysisTask(Base):
    """
    Отслеживает задачу анализа изображения.
    Не содержит чувствительных данных — только внутренние ID.
    """
    __tablename__ = 'analysis_tasks'
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Связь с изображением (через него найдём user_id, project_id)
    image_id = Column(PG_UUID(as_uuid=True), ForeignKey('images.id'), nullable=False, index=True)
    
    # Какой сервис/модель запрашиваем
    model_config_id = Column(Integer, ForeignKey('models.id'), nullable=False)

    # Список ID классов для анализа (хранится как JSONB в PostgreSQL)
    class_type_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=True, default=[])

    # Статус и метаданные
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.pending, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Сообщение-ошибка сохраняется 
    error_message = Column(String(500), nullable=True)
    
    # Для WebSocket: идентификатор сессии клиента (опционально)
    ws_session_id = Column(String(255), nullable=True, index=True)
    
    # Relationships
    image = relationship("Image", back_populates="analysis_tasks")
    model_config = relationship("ModelConfig")