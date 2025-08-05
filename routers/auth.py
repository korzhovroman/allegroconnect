# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select # <-- Импортируем select

from models.database import get_db
from models.models import User
from schemas.user import UserResponse
from schemas.token import TokenPayload
from services.user_service import UserService
from utils.auth import verify_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def get_user_service() -> UserService:
    return UserService()

@router.post("/sync-user", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def sync_supabase_user(
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(verify_token)
):
    if not token_payload.sub or not token_payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token must contain sub (ID) and email."
        )

    # Ищем пользователя по НЕИЗМЕНЯЕМОМУ ID из Supabase
    query = select(User).where(User.supabase_user_id == token_payload.sub)
    result = await db.execute(query)
    db_user = result.scalar_one_or_none()

    # Если нашли пользователя, то просто вернем его
    if db_user:
        # Опционально: если email в токене не совпадает с email в нашей БД,
        # значит, пользователь его сменил. Обновим его у себя.
        if db_user.email != token_payload.email:
            db_user.email = token_payload.email
            await db.commit()
            await db.refresh(db_user)
        return db_user

    # Если пользователя с таким supabase_user_id нет, создаем его
    new_user = User(
        supabase_user_id=token_payload.sub,
        email=token_payload.email,
        hashed_password="not_used"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user
Шаг 4: Обновите зависимость get_current_user
Наконец, изменим get_current_user, чтобы он тоже искал пользователя по supabase_user_id.

Python

# utils/dependencies.py
# ... импорты
from sqlalchemy import select

# ...

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
