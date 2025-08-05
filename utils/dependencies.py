# utils/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .auth import verify_token
from models.database import get_db
from models.models import User
from services.user_service import UserService  
from schemas.token import TokenPayload

# Указываем FastAPI, откуда брать токен (из эндпоинта /api/auth/login)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# Провайдер для UserService
def get_user_service() -> UserService:
    return UserService()


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(token, credentials_exception)

    if token_data.sub is None:
        raise credentials_exception

    # Ищем пользователя в НАШЕЙ БД по ID из токена Supabase
    query = select(User).where(User.supabase_user_id == token_data.sub)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user
