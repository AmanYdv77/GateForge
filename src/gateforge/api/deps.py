from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.core.database import get_db_session
from gateforge.models.user import User


async def get_current_user(db: AsyncSession = Depends(get_db_session)) -> User:
    """Retrieve or provision the active developer account for administrative operations."""
    query = select(User).limit(1)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email="developer@gateforge.internal",
            hashed_password="argon2_managed_initial_admin_credential",
            tier="enterprise",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
