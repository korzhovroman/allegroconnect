# services/user_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from models.models import User
from schemas.user import UserCreate
from utils.security import hash_password, verify_password


class UserService:

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> User | None:
        """Асинхронно получает пользователя по ID."""
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Асинхронно получает пользователя по email."""
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_user(self, db: AsyncSession, user_data: UserCreate) -> User:
        """Асинхронно создает нового пользователя."""
        # 3. Используем собственный метод для проверки (принцип DRY)
        existing_user = await self.get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже существует."
            )

        hashed_pass = hash_password(user_data.password)
        new_user = User(email=user_data.email, hashed_password=hashed_pass)

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    async def authenticate_user(self, db: AsyncSession, email: str, password: str) -> User | None:
        """
        Асинхронно аутентифицирует пользователя.
        Возвращает объект User в случае успеха или None в случае неудачи.
        """
        user = await self.get_user_by_email(db, email)

        if not user or not verify_password(password, user.hashed_password):
            return None  # Просто возвращаем None, без ошибки

        return user