"""Workspace CRUD endpoints + sharing + code execution."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Workspace
from app.schemas.workspace import (
    WorkspaceCreate, WorkspaceUpdate, WorkspaceOut, WorkspaceList,
    ShareRequest, MemberOut, MemberList,
    ExecuteRequest, ExecuteResponse,
)
from app.services import workspace_service
from app.services import sharing_service
from app.services import executor_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ── Core CRUD (now access-aware: owner OR member) ───────────────────────────

@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload:      WorkspaceCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceOut:
    workspace = workspace_service.create_workspace_for_user(db, current_user, payload)
    return WorkspaceOut.model_validate(workspace)


@router.get("", response_model=WorkspaceList)
def list_workspaces(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceList:
    items = sharing_service.get_accessible_workspaces(db, current_user.id)
    return WorkspaceList(total=len(items),
                         items=[WorkspaceOut.model_validate(w) for w in items])


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceOut:
    workspace = sharing_service.get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceOut.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: int,
    payload:      WorkspaceUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceOut:
    workspace = sharing_service.get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if payload.name is not None:
        workspace.name = payload.name
    if payload.status is not None:
        workspace.status = payload.status

    db.commit()
    db.refresh(workspace)
    return WorkspaceOut.model_validate(workspace)


@router.post("/{workspace_id}/start", response_model=WorkspaceOut)
def start_workspace(
    workspace_id: int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceOut:
    workspace = sharing_service.get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.status == "RUNNING":
        return WorkspaceOut.model_validate(workspace)
    workspace_service.transition_status(db, workspace, "RUNNING")
    return WorkspaceOut.model_validate(workspace)


@router.post("/{workspace_id}/stop", response_model=WorkspaceOut)
def stop_workspace(
    workspace_id: int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> WorkspaceOut:
    workspace = sharing_service.get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace_service.transition_status(db, workspace, "STOPPED")
    return WorkspaceOut.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> None:
    # Only the OWNER can delete (not collaborators)
    if not sharing_service.user_owns(db, workspace_id, current_user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    db.delete(workspace)
    db.commit()


# ── Sharing endpoints ───────────────────────────────────────────────────────

@router.get("/{workspace_id}/members", response_model=MemberList)
def list_members(
    workspace_id: int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> MemberList:
    if not sharing_service.user_can_access(db, workspace_id, current_user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    items = sharing_service.list_members(db, workspace_id)
    return MemberList(total=len(items), items=items)


@router.post("/{workspace_id}/share", status_code=status.HTTP_201_CREATED)
def share_workspace(
    workspace_id: int,
    payload:      ShareRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> dict:
    """Invite another user as a collaborator (editor or viewer)."""
    member = sharing_service.share_workspace(
        db, workspace_id, current_user.id,
        target_username=payload.username, role=payload.role,
    )
    return {
        "workspace_id": workspace_id,
        "user_id":      member.user_id,
        "username":     payload.username,
        "role":         member.role,
    }


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: int,
    user_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> None:
    """Remove a collaborator. Only the owner can do this."""
    removed = sharing_service.unshare_workspace(db, workspace_id, current_user.id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")


# ── Code execution ──────────────────────────────────────────────────────────

@router.post("/{workspace_id}/execute", response_model=ExecuteResponse)
def execute_code(
    workspace_id: int,
    payload:      ExecuteRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> ExecuteResponse:
    """
    Run the given code in the requested language and return stdout/stderr.

    This is the demo executor — production execution should route through
    the workspace's assigned sandbox pod (Phase 3+).
    """
    if not sharing_service.user_can_access(db, workspace_id, current_user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    result = executor_service.execute(
        language=payload.language,
        code=payload.code,
        stdin=payload.stdin,
    )
    return ExecuteResponse(
        language=result.language,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        runtime_ms=result.runtime_ms,
        timeout=result.timeout,
        truncated=result.truncated,
    )
