from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Team(Base):
    __tablename__ = 'teams'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, default="Mój zespół")
    owner_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    owner = relationship("User", back_populates="owned_team")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")

class TeamMember(Base):
    __tablename__ = 'team_members'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    team_id = Column(Integer, ForeignKey('teams.id', ondelete="CASCADE"), nullable=False)
    role = Column(String, default='employee', nullable=False)  
    user = relationship("User", back_populates="team_membership")
    team = relationship("Team", back_populates="members")
    permissions = relationship("EmployeePermission", back_populates="member", cascade="all, delete-orphan")


class EmployeePermission(Base):
    __tablename__ = 'employee_permissions'
    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey('team_members.id', ondelete="CASCADE"), nullable=False)
    allegro_account_id = Column(Integer, ForeignKey('allegro_accounts.id', ondelete="CASCADE"), nullable=False)
    member = relationship("TeamMember", back_populates="permissions")
    allegro_account = relationship("AllegroAccount")


class MessageMetadata(Base):
    __tablename__ = 'message_metadata'
    id = Column(Integer, primary_key=True, index=True)
    allegro_message_id = Column(String, unique=True, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)
    sent_by_user_id = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    sender = relationship("User")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    supabase_user_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True) 
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    subscription_status = Column(String, default='free', nullable=False)
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)
    fcm_token = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    nip = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    owned_team = relationship("Team", back_populates="owner", uselist=False, cascade="all, delete-orphan")
    team_membership = relationship("TeamMember", back_populates="user", uselist=False, cascade="all, delete-orphan")
    allegro_accounts = relationship("AllegroAccount", back_populates="owner", cascade="all, delete-orphan")


class AllegroAccount(Base):
    __tablename__ = "allegro_accounts"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False)  
    allegro_user_id = Column(String, nullable=False)
    allegro_login = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    auto_reply_enabled = Column(Boolean, default=False)
    auto_reply_text = Column(String, nullable=True)
    owner = relationship("User", back_populates="allegro_accounts")

class AutoReplyLog(Base):
    __tablename__ = 'auto_reply_log'
    conversation_id = Column(String, primary_key=True)
    allegro_account_id = Column(Integer, ForeignKey('allegro_accounts.id'), primary_key=True)
    reply_time = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class TaskQueue(Base):
    __tablename__ = 'task_queue'
    id = Column(Integer, primary_key=True, index=True)
    allegro_account_id = Column(Integer, ForeignKey('allegro_accounts.id', ondelete="CASCADE"), unique=True, nullable=False)
    status = Column(String, default='pending', index=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)