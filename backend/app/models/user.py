"""User model."""
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id:              Mapped[int]      = mapped_column(primary_key=True, index=True)
    email:           Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    username:        Mapped[str]      = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str]      = mapped_column(String(255))
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True)
    trust_score:     Mapped[float]    = mapped_column(Float, default=0.5)  # Used by risk scorer
    preferred_lang:  Mapped[str]      = mapped_column(String(32), default="python")
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workspaces = relationship("Workspace", back_populates="owner", cascade="all, delete-orphan")
