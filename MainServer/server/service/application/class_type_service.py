import asyncio
from typing import List, Dict
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
import logging

from server.core.dependencies import TranslationService
from server.service.dal.repositories import ClassTypeRepository


class ClassTypeService:
    @staticmethod
    async def ensure_and_map_class_types(
        db: AsyncSession,
        project_id: str,
        class_names: List[str],
        logger: logging.Logger
    ) -> Dict[str, str]:
        """
        Гарантирует наличие классов в БД и возвращает маппинг {любое_имя → английское_имя}.
        """
        if not class_names:
            return {}

        unique_names = list(set(class_names))
        
        existing = await ClassTypeRepository.find_existing_by_names(
            db, project_id, unique_names
        )
        
        name_to_en: Dict[str, str] = {}
        for ct in existing:
            name_to_en[ct.name_ru] = ct.name_eng
            name_to_en[ct.name_eng] = ct.name_eng
            
        missing = [n for n in unique_names if n not in name_to_en]
        
        if missing:
            translator = TranslationService()
            translations = await asyncio.to_thread(
                translator.translate_list, missing, 'ru', 'en'
            )
            
            new_entries_data = [
                {'name_ru': ru, 'name_eng': en}
                for ru, en in zip(missing, translations)
            ]
            await ClassTypeRepository.create_many(db, project_id, new_entries_data)
            
            for ru, en in zip(missing, translations):
                name_to_en[ru] = en
                
        logger.info(
            f"ClassTypeService: проект {project_id}, "
            f"обработано {len(unique_names)} классов, создано {len(missing)} новых"
        )
        return name_to_en