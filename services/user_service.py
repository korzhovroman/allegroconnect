from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.models import User
from schemas.user import UserCreate
from utils.auth import get_password_hash, verify_password
from fastapi import HTTPException, status


class UserService:

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        # Проверка существования пользователя
        result = await db.execute(select(User).filter(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"  # Исправлена кавычка
            )

        # Создание пользователя
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            hashed_password=hashed_password
        )

        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        return db_user

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        return user