from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, or_
from typing import List
from uuid import UUID

from server.service.dal.repositories.base_repository import BaseRepository
from server.service.db.shemas.models import User, UserDefinition, RefreshToken, UserType


class UserRepository(BaseRepository[User]):
    model = User

    @classmethod
    async def search_users(cls, db: AsyncSession, query: str, limit: int = 20) -> List[User]:
        """Поиск по email, login или названию компании (из UserDefinition)"""
        stmt = (
            select(User)
            .outerjoin(UserDefinition, User.definition_id == UserDefinition.id)
            .where(
                or_(
                    User.email.ilike(f"%{query}%"),
                    User.login.ilike(f"%{query}%"),
                    UserDefinition.name_company.ilike(f"%{query}%")
                )
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


class UserDefinitionRepository(BaseRepository[UserDefinition]):
    model = UserDefinition


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    @classmethod
    async def delete_by_user_id(cls, db: AsyncSession, user_id: UUID) -> bool:
        result = await db.execute(
            delete(cls.model)
            .where(cls.model.user_id == user_id)
        )
        return result.rowcount > 0
