from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    supabase_user_id = Column(String, unique=True, index=True, nullable=True)
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
    auto_reply_enabled = Column(Boolean, default=False)
    auto_reply_text = Column(String, nullable=True)

    # Relationship
    owner = relationship("User", back_populates="allegro_accounts")

class AutoReplyLog(Base):
    __tablename__ = 'auto_reply_log'

    # Составной первичный ключ, чтобы для каждого вашего аккаунта
    # можно было отслеживать свои диалоги
    conversation_id = Column(String, primary_key=True)
    allegro_account_id = Column(Integer, ForeignKey('allegro_accounts.id'), primary_key=True)

    reply_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
