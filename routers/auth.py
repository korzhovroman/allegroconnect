from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from models.database import get_db
from schemas.user import UserCreate, UserLogin, UserResponse, Token
from services.user_service import UserService
from utils.auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
        user_data: UserCreate,
        db: AsyncSession = Depends(get_db)
):
    """Регистрация нового пользователя"""
    user = await UserService.create_user(db, user_data)
    return user


@router.post("/login", response_model=Token)
async def login_user(
        login_data: UserLogin,
        db: AsyncSession = Depends(get_db)
):
    """Вход пользователя и получение JWT токена"""
    user = await UserService.authenticate_user(db, login_data.email, login_data.password)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}