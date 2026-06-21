"""
Workspace sharing — invite other users to collaborate on a workspace.

Permissions model:
  - owner:   full control (delete, share, manage members)
  - editor:  can edit code + start/stop, cannot delete or share
  - viewer:  read-only (future use)

The original creator (workspaces.owner_id) is always the owner. Additional
collaborators are stored in the `workspace_members` table.
"""
from __future__ import annotations
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import User, Workspace, WorkspaceMember


# ── Access checks ──────────────────────────────────────────────────────────

def user_can_access(db: Session, workspace_id: int, user_id: int) -> bool:
    """True if user is the owner OR an active member of the workspace."""
    if db.query(Workspace).filter(
        Workspace.id == workspace_id, Workspace.owner_id == user_id
    ).first():
        return True
    return db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    ).first() is not None


def user_owns(db: Session, workspace_id: int, user_id: int) -> bool:
    return db.query(Workspace).filter(
        Workspace.id == workspace_id, Workspace.owner_id == user_id
    ).first() is not None


def get_accessible_workspaces(db: Session, user_id: int) -> List[Workspace]:
    """
    Returns workspaces the user can access — both owned and shared.
    Ordered newest first by creation time.
    """
    owned_ids = select(Workspace.id).where(Workspace.owner_id == user_id)
    shared_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == user_id
    )
    return (
        db.query(Workspace)
        .filter(or_(Workspace.id.in_(owned_ids), Workspace.id.in_(shared_ids)))
        .order_by(Workspace.created_at.desc())
        .all()
    )


def get_workspace_for_user(db: Session, workspace_id: int, user_id: int) -> Optional[Workspace]:
    """Fetch a workspace ONLY if the user can access it."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if workspace is None:
        return None
    if workspace.owner_id == user_id:
        return workspace
    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    ).first()
    return workspace if member else None


# ── Sharing operations ─────────────────────────────────────────────────────

def share_workspace(
    db: Session, workspace_id: int, owner_user_id: int,
    target_username: str, role: str = "editor",
) -> WorkspaceMember:
    if not user_owns(db, workspace_id, owner_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can share it",
        )

    target = db.query(User).filter(User.username == target_username).first()
    if target is None:
        raise HTTPException(404, f"User '{target_username}' not found")
    if target.id == owner_user_id:
        raise HTTPException(400, "Cannot share workspace with yourself")
    if role not in ("editor", "viewer"):
        raise HTTPException(400, f"Invalid role '{role}'. Must be 'editor' or 'viewer'")

    existing = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == target.id,
    ).first()
    if existing:
        existing.role = role
        db.commit()
        return existing

    member = WorkspaceMember(
        workspace_id=workspace_id, user_id=target.id, role=role,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def unshare_workspace(
    db: Session, workspace_id: int, owner_user_id: int, target_user_id: int,
) -> bool:
    if not user_owns(db, workspace_id, owner_user_id):
        raise HTTPException(403, "Only the workspace owner can manage members")

    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == target_user_id,
    ).first()
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


def list_members(db: Session, workspace_id: int) -> List[dict]:
    """Returns owner + all collaborators with role info, sorted by added_at."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if workspace is None:
        return []

    # Owner is "added" at workspace creation time
    members: List[dict] = [{
        "user_id":  workspace.owner.id,
        "username": workspace.owner.username,
        "email":    workspace.owner.email,
        "avatar_url": getattr(workspace.owner, "avatar_url", None),
        "role":     "owner",
        "added_at": workspace.created_at,
    }]
    for m in workspace.members:
        members.append({
            "user_id":  m.user.id,
            "username": m.user.username,
            "email":    m.user.email,
            "avatar_url": getattr(m.user, "avatar_url", None),
            "role":     m.role,
            "added_at": m.added_at,
        })
    return members
