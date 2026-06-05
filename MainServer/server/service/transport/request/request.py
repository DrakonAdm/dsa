from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Union, List, Dict, Any, Literal
from uuid import UUID
from enum import Enum

class AnnotationTypeEnum(str, Enum):
    detection = "detection"
    segmentation = "segmentation"


class AnnotationCreate(BaseModel):
    type: Literal['detect', 'segment', 'detection', 'segmentation'] = Field(
        default='detection', 
        description="Тип аннотации: 'detect'/'segment' во входящем запросе или 'detection'/'segmentation' для совместимости"
    )
    class_name: str = Field(description="Класс объекта")
    data: list = Field(description="Координаты/данные аннотации (JSONB)")

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v):
        if hasattr(v, 'value'):
            v = v.value
        return {
            'detect': 'detection',
            'segment': 'segmentation',
            'detection': 'detection',
            'segmentation': 'segmentation'
        }.get(v, v)


class MaskCreate(BaseModel):
    class_name: str = Field(description="Класс объекта")
    width: Optional[int] = Field(default=None, description="Ширина изображения")
    height: Optional[int] = Field(default=None, description="Высота изображения")
    format: Optional[str] = Field(default=None, description="Формат изображения jpg/png/tiff...")


class ImageUploadRequest(BaseModel):
    width: Optional[int] = Field(default=None, description="Ширина изображения")
    height: Optional[int] = Field(default=None, description="Высота изображения")
    format: Optional[str] = Field(default=None, description="Формат изображения jpg/png/tiff...")
    annotations: List[AnnotationCreate] = Field(default_factory=list)
    masks: List[MaskCreate] = Field(default_factory=list)


class ListImageLoadRequest(BaseModel):
    metadata: Optional[list[ImageUploadRequest]] = Field(default=None, description="Список метаданных для изображений")


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Название проекта")


class ClassTypeCreate(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=80, description="Название класса на русском")
    name_eng: Optional[str] = Field(None, max_length=80, description="Название класса на английском")
    model_config = {"validate_default": True}

    @model_validator(mode='after')
    def check_at_least_one_name(self):
        if not self.name_ru and not self.name_eng:
            raise ValueError("Необходимо указать хотя бы одно название: name_ru или name_eng")
        return self


class AddMemberRequest(BaseModel):
    email: Optional[str] = None
    login: Optional[str] = None
    model_config = {"validate_default": True}


class AnnotationUpdate(BaseModel):
    """Для обновления одной аннотации через PUT (id берётся из path)"""
    type: Optional[Literal['detect', 'segment', 'detection', 'segmentation']] = None
    class_name: Optional[str] = None
    data: Optional[Any] = None
    is_selected: Optional[bool] = None

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v):
        if hasattr(v, 'value'):
            v = v.value
        return {
            'detect': 'detection',
            'segment': 'segmentation'
        }.get(v, v)


class AnnotationBatchUpdate(BaseModel):
    """Для пакетного обновления (id указывается в теле)"""
    id: UUID = Field(..., description="UUID аннотации")
    type: Optional[Literal['detect', 'segment', 'detection', 'segmentation']] = None
    class_name: Optional[str] = None
    data: Optional[Any] = None
    is_selected: Optional[bool] = None

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v):
        if hasattr(v, 'value'):
            v = v.value
        return {
            'detect': 'detection',
            'segment': 'segmentation'
        }.get(v, v)

