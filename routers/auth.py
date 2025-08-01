from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем наш объект настроек
from ..config import settings
from ..models.database import get_db
from ..schemas.user import UserCreate, UserResponse, Token
from ..services.user_service import UserService
# Функцию create_access_token нужно будет немного изменить
from ..utils.auth import create_access_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Провайдер зависимости для UserService
def get_user_service() -> UserService:
    return UserService()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service) # <-- Внедряем сервис
):
    """Регистрация нового пользователя"""
    # Вызываем метод экземпляра
    user = await user_service.create_user(db, user_data)
    return user


@router.post("/login", response_model=Token)
async def login_for_access_token(
    # Используем стандартную форму FastAPI для получения email/password
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service) # <-- Внедряем сервис
):
    """Аутентификация пользователя и выдача JWT токена."""
    user = await user_service.authenticate_user(db, email=form_data.username, password=form_data.password)

    # Создаем токен
    access_token = create_access_token(
        data={"sub": user.email} # Используем email как subject токена
    )

    return {"access_token": access_token, "token_type": "bearer"}