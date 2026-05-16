from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.log.logger import Logger
from server.service.transport.user_transport import UserBase, UserDefinitionBase
from server.service.dal.repositories.user_repository import UserRepository, UserDefinitionRepository
from server.core.dependencies import get_definition_user, search_check_user

class DataBaseDataUserService:
    async def change_login_user(logger: Logger,
                                new_login: UserBase,
                                token: str,
                                db: AsyncSession
                                ):
        logger = logger.class_log("DataBaseDataUser")

        try:
            user = await search_check_user(token=token, logger=logger, db=db)
        except Exception:
            raise

        user_understudy = await UserRepository.find_one_or_none(db, login=new_login.login)
        if user_understudy:
            logger.get_debug(f"Найден пользователь при смени логина")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Такой логин уже есть')
        
        user.login = new_login.login
        # await db.commit()

        return UserBase(
            login=user.login,
        )
    
    async def change_definition_user(logger: Logger,
                                     new_definition: UserDefinitionBase,
                                     token: str,
                                     db: AsyncSession
                                     ):
        logger = logger.class_log("DataBaseDataUser")

        try:
            user_def = await get_definition_user(token=token, logger=logger, db=db)
            if user_def is None:
                user = await search_check_user(token=token, logger=logger, db=db)
                user_def = UserDefinitionRepository.create(db=db)
                await db.flush() 
                user.definition_id = user_def.id
                # await db.commit() 
        except Exception:
            await db.rollback()
            raise

        if new_definition.definition is not None:
            user_def.definition = new_definition.definition
        if new_definition.name_company is not None:
            user_def.name_company = new_definition.name_company

        # await db.commit()
        
        return UserDefinitionBase(
            name_company=user_def.name_company,
            definition=user_def.definition
        )

    async def get_current_user(logger: Logger, 
                               token: str, 
                               db: AsyncSession
                               ):
        logger = logger.class_log("DataBaseDataUser")

        try:
            user = await search_check_user(token=token, logger=logger, db=db)
        except Exception:
            raise

        return UserBase(
            login=user.login,
        )

    async def get_current_definition_user(logger: Logger, 
                                          token: str, 
                                          db: AsyncSession
                                          ):
        logger = logger.class_log("DataBaseDataUser")
        
        try:
            user_def = await get_definition_user(token=token, logger=logger, db=db)
            if user_def is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Неверный тип токена')
        except Exception:
            raise

        return UserDefinitionBase(
            name_company=user_def.name_company,
            definition=user_def.definition
        )
