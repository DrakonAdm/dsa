from sqladmin import ModelView, Admin
import json
from uuid import UUID
from wtforms.fields import StringField
from wtforms.widgets import TextArea

from server.service.db.shemas.models import *
from passlib.context import CryptContext
from sqlalchemy.orm import Mapper
from sqlalchemy import event

class UUIDArrayStringField(StringField):
    """
    Поле для работы с массивом UUID как с JSON-строкой.
    При отображении: UUID -> str, при сохранении: str -> UUID.
    """
    widget = TextArea()
    
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            try:
                data = json.loads(valuelist[0])
                # Конвертируем строки обратно в UUID
                self.data = [UUID(item) for item in data if item]
            except (json.JSONDecodeError, ValueError, TypeError):
                self.data = []
        else:
            self.data = []
    
    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        if self.data and isinstance(self.data, list):
            # Конвертируем UUID в строки для безопасной сериализации
            return json.dumps([str(uuid) for uuid in self.data if uuid])
        return '[]'


class UserAdmin(ModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    
    column_list = ["id", "login", "definition", "time_created_password"]
    column_searchable_list = ["id", "login", "time_created_password"]
    column_sortable_list = ["id", "login", "time_created_password"]
    
    # Разрешаем редактирование
    can_edit = True
    form_columns = ["hashed_password", "definition"]  # Добавляем поле password
    
    form_ajax_refs = {
        'definition': {
            'fields': ('name_company', 'definition'),
            'order_by': 'name_company',
        }
    }
    
    form_widget_args = {
        "login": {
            "readonly": True
        },
        "hashed_password": {
            "type": "hashed_password"  # Делаем поле пароля скрытым при вводе
        }
    }
    
    async def update_model(self, request, pk, data):
        """Переопределяем сохранение модели"""
        if "hashed_password" in data and data["hashed_password"]:
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            data["hashed_password"] = pwd_context.hash(data["hashed_password"])
        
        return await super().update_model(request, pk, data)

class UserDefinitionAdmin(ModelView, model=UserDefinition):
    name = "Параметров Пользователя"
    name_plural = "Параметры Пользователя"
    
    column_list = ["id", "name_company", "definition", "user"]
    column_searchable_list = ["name_company", "id"]
    column_sortable_list = ["id"]
    
    form_ajax_refs = {
        'user': {
            'fields': ('login',),
            'order_by': 'login',
        }
    }

class ImageAdmin(ModelView, model=Image):
    name = "Изображение"
    name_plural = "Изображения"
    icon = "fa-solid fa-image"
    
    column_list = ["id", "file_path", "width", "height", "format"]
    column_searchable_list = ["id", "file_path", "format"]
    column_sortable_list = ["id", "width", "height"]
    
    can_edit = True
    can_create = True
    form_columns = ["file_path", "width", "height", "format"]

class ModelConfigAdmin(ModelView, model=ModelConfig):
    name = "ML Модель"
    name_plural = "ML Модели"
    icon = "fa-solid fa-robot"
    
    column_list = ["id", "name", "type", "endpoint_url", "is_active"]
    column_searchable_list = ["name", "type", "endpoint_url"]
    column_sortable_list = ["id", "name", "is_active"]
    
    can_edit = True
    can_create = True
    form_columns = ["name", "type", "endpoint_url", "is_active"]

class ProjectAdmin(ModelView, model=Project):
    name = "Проект"
    name_plural = "Проекты"
    icon = "fa-solid fa-folder"
    
    column_list = ["id", "name", "creator", "created_at"]
    column_searchable_list = ["name"]
    column_sortable_list = ["id", "name", "created_at"]
    
    can_edit = True
    can_create = True
    # created_at и created_by_id управляются автоматически или через creator
    form_columns = ["name", "creator"] 
    
    form_ajax_refs = {
        'creator': {'fields': ('login',), 'order_by': 'login'}
    }

class AnnotationAdmin(ModelView, model=Annotation):
    name = "Разметка"
    name_plural = "Разметки"
    icon = "fa-solid fa-tag"
    
    column_list = ["id", "image", "type", "class_name", "is_selected"]
    column_searchable_list = ["class_name", "type"]
    column_sortable_list = ["id", "class_name"]
    
    can_edit = True
    can_create = True
    form_columns = ["image", "type", "class_name", "data", "is_selected"]
    
    form_ajax_refs = {
        'image': {'fields': ('file_path',), 'order_by': 'file_path'}
    }

class MaskAdmin(ModelView, model=Mask):
    name = "Маска"
    name_plural = "Маски"
    icon = "fa-solid fa-mask"
    
    column_list = ["id", "image", "file_path", "width", "height", "format"]
    column_searchable_list = ["file_path", "format"]
    can_edit = True
    can_create = True
    form_columns = ["image", "file_path", "width", "height", "format"]
    
    form_ajax_refs = {
        'image': {'fields': ('file_path',), 'order_by': 'file_path'}
    }

class AnalysisTaskAdmin(ModelView, model=AnalysisTask):
    name = "Задача анализа"
    name_plural = "Задачи анализа"
    icon = "fa-solid fa-chart-line"
    
    column_list = ["id", "image", "model_config", "status", "created_at", "completed_at"]
    column_searchable_list = ["id", "status", "error_message"]
    column_sortable_list = ["id", "status", "created_at", "completed_at"]
    
    can_edit = True
    can_create = True
    form_columns = ["image", "model_config", "class_type_ids", "status", "error_message", "ws_session_id"]
    
    form_ajax_refs = {
        'image': {'fields': ('file_path',), 'order_by': 'file_path'},
        'model_config': {'fields': ('name',), 'order_by': 'name'}
    }

    form_overrides = {
        'class_type_ids': UUIDArrayStringField
    }
    
    form_widget_args = {
        "class_type_ids": {"placeholder": 'Массив UUID: ["uuid-1", "uuid-2"]'},
        "error_message": {"rows": 3, "placeholder": "Описание ошибки (если есть)"}
    }

class ClassTypeProjectAdmin(ModelView, model=ClassTypeProject):
    name = "Класс проекта"
    name_plural = "Классы проектов"
    icon = "fa-solid fa-tags"
    
    column_list = ["id", "name_ru", "name_eng", "project"]
    column_searchable_list = ["name_ru", "name_eng"]
    column_sortable_list = ["id", "name_ru"]
    
    can_edit = True
    can_create = True
    form_columns = ["name_ru", "name_eng", "project"]
    
    form_ajax_refs = {
        'project': {'fields': ('name',), 'order_by': 'name'}
    }

class OAuthAccountAdmin(ModelView, model=OAuthAccount):
    name = "OAuth аккаунт"
    name_plural = "OAuth аккаунты"
    icon = "fa-solid fa-globe"
    
    column_list = ["id", "user", "provider", "provider_user_id"]
    column_searchable_list = ["provider", "provider_user_id"]
    column_sortable_list = ["provider", "id"]
    
    can_edit = True
    can_create = True
    form_columns = ["user", "provider", "provider_user_id"]
    
    form_ajax_refs = {
        'user': {'fields': ('login',), 'order_by': 'login'}
    }

def _on_class_table_change(mapper: Mapper, connection, target) -> None:
    """Сброс кэша при любом изменении в справочниках классов."""
    # импорт внутри, чтобы избежать циклической зависимости
    from server.service.dal.repositories.cache_repository import CacheObjectClassesRepository
    CacheObjectClassesRepository.invalidate_cache()


def add_custom_view(admin: Admin):
    admin.add_view(UserAdmin)
    admin.add_view(UserDefinitionAdmin)
    admin.add_view(ImageAdmin)
    admin.add_view(ModelConfigAdmin)
    admin.add_view(ProjectAdmin)
    admin.add_view(AnnotationAdmin)
    admin.add_view(MaskAdmin)
    admin.add_view(AnalysisTaskAdmin)
    admin.add_view(ClassTypeProjectAdmin)


def add_event_listen():
    event.listen(ModelConfig, 'after_insert', _on_class_table_change)
    event.listen(ModelConfig, 'after_update', _on_class_table_change)
    event.listen(ModelConfig, 'after_delete', _on_class_table_change)
