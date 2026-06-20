"""User model."""
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id:              Mapped[int]      = mapped_column(primary_key=True, index=True)
    email:           Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    username:        Mapped[str]      = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str]      = mapped_column(String(255))
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True)
    is_admin:        Mapped[bool]     = mapped_column(Boolean, default=False)
    trust_score:     Mapped[float]    = mapped_column(Float, default=0.5)  # Used by risk scorer
    preferred_lang:  Mapped[str]      = mapped_column(String(32), default="python")
    avatar_url:      Mapped[str]      = mapped_column(String(512), nullable=True)  # imgbb-hosted profile image
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── GitHub OAuth ──────────────────────────────────────────────────────────
    github_id:           Mapped[int | None]  = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    github_login:        Mapped[str | None]  = mapped_column(String(128), nullable=True)  # GitHub username
    github_access_token: Mapped[str | None]  = mapped_column(String(2048), nullable=True)  # Fernet-encrypted

    workspaces = relationship("Workspace", back_populates="owner", cascade="all, delete-orphan")
