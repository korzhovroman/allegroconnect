from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
# 'datetime' не используется, можно удалить, но не является ошибкой
# from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    allegro_accounts = relationship("AllegroAccount", back_populates="owner", cascade="all, delete-orphan")


class AllegroAccount(Base):
    __tablename__ = "allegro_accounts"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    allegro_user_id = Column(String, nullable=False)
    allegro_login = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)  # зашифрованный
    refresh_token = Column(Text, nullable=False)  # зашифрованный
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    owner = relationship("User", back_populates="allegro_accounts")