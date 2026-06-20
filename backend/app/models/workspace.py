"""Workspace model — represents a user's cloud IDE instance."""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Float, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# Workspace lifecycle: PENDING → PREWARMED → RUNNING → STOPPED → ARCHIVED
WORKSPACE_STATUSES = ("PENDING", "PREWARMED", "RUNNING", "STOPPED", "FAILED", "ARCHIVED")

# Sandbox tiers: runc (fast) → gvisor (medium isolation) → firecracker (microVM)
SANDBOX_TIERS = ("runc", "gvisor", "firecracker")

# Member roles
MEMBER_ROLES = ("owner", "editor", "viewer")


class Workspace(Base):
    __tablename__ = "workspaces"

    id:              Mapped[int]      = mapped_column(primary_key=True, index=True)
    name:            Mapped[str]      = mapped_column(String(128))
    language:        Mapped[str]      = mapped_column(String(32), default="python")
    status:          Mapped[str]      = mapped_column(String(16), default="PENDING")
    sandbox_tier:    Mapped[str]      = mapped_column(String(16), default="runc")
    risk_score:      Mapped[float]    = mapped_column(Float, default=0.0)
    network_access:  Mapped[bool]     = mapped_column(Boolean, default=False)
    filesystem_write: Mapped[bool]    = mapped_column(Boolean, default=True)
    cpu_request:     Mapped[float]    = mapped_column(Float, default=0.5)        # cores
    memory_request:  Mapped[int]      = mapped_column(Integer, default=512)      # MiB
    cluster_id:      Mapped[str]      = mapped_column(String(64), default="local")
    node_name:       Mapped[str]      = mapped_column(String(128), default="")
    pod_name:        Mapped[str]      = mapped_column(String(128), default="")
    yjs_room:        Mapped[str]      = mapped_column(String(64), default="")
    initial_code:    Mapped[str]      = mapped_column(Text, default="")
    forked_from_id:  Mapped[int]      = mapped_column(Integer, nullable=True)  # source workspace if forked
    frozen:          Mapped[bool]     = mapped_column(Boolean, default=False)  # read-only lock (settings)
    shared_excludes: Mapped[str]      = mapped_column(Text, default="")        # JSON list of paths hidden from members
    owner_id:        Mapped[int]      = mapped_column(ForeignKey("users.id"))
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner   = relationship("User", back_populates="workspaces")
    members = relationship("WorkspaceMember", back_populates="workspace",
                           cascade="all, delete-orphan", lazy="select")


class WorkspaceMember(Base):
    """
    Many-to-many between users and workspaces for collaborative access.
    The workspace's `owner_id` field is the primary owner; this table tracks
    additional collaborators who can read/edit but not delete or share further.
    """
    __tablename__ = "workspace_members"

    workspace_id: Mapped[int]      = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id:      Mapped[int]      = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role:         Mapped[str]      = mapped_column(String(16), default="editor")
    added_at:     Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="members")
    user      = relationship("User")


class WorkspaceEdit(Base):
    """
    Change-history log (Google-Docs style). One row per file save, recording who
    saved, which file, and how many lines changed. Only the workspace owner can
    read the history; forks accumulate their own (separate workspace_id).
    """
    __tablename__ = "workspace_edits"

    id:           Mapped[int]      = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int]      = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id:      Mapped[int]      = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username:     Mapped[str]      = mapped_column(String(64), default="")
    path:         Mapped[str]      = mapped_column(String(400), default="")
    lines_added:  Mapped[int]      = mapped_column(Integer, default=0)
    lines_removed: Mapped[int]     = mapped_column(Integer, default=0)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
