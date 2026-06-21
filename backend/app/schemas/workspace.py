"""Pydantic schemas for workspace endpoints."""
from datetime import datetime, timezone
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, field_serializer

# Manual sandbox-tier pin. None = adaptive (risk-scored) selection.
SandboxOverride = Optional[Literal["runc", "gvisor", "firecracker"]]


class WorkspaceCreate(BaseModel):
    name:             str  = Field(min_length=1, max_length=128)
    language:         str  = Field(default="python", max_length=32)
    network_access:   bool = False
    filesystem_write: bool = True
    cpu_request:      float = Field(default=0.5, gt=0, le=8)
    memory_request:   int   = Field(default=512, gt=0, le=16384)
    initial_code:     str   = ""
    # None = "Auto" (adaptive risk scoring); otherwise pin the tier explicitly.
    sandbox_override: SandboxOverride = None


class WorkspaceUpdate(BaseModel):
    name:   Optional[str] = None
    status: Optional[str] = None
    # Re-pin the sandbox tier after creation (owner action).
    sandbox_override: SandboxOverride = None
    frozen: Optional[bool] = None          # read-only lock (settings panel)


class WorkspaceOut(BaseModel):
    id:               int
    name:             str
    language:         str
    status:           str
    sandbox_tier:     str
    risk_score:       float
    network_access:   bool
    filesystem_write: bool
    cpu_request:      float
    memory_request:   int
    cluster_id:       str
    node_name:        str
    pod_name:         str
    yjs_room:         str
    owner_id:         int
    forked_from_id:   Optional[int] = None
    frozen:           bool = False
    created_at:       datetime
    updated_at:       datetime
    last_active_at:   datetime

    # DB stores naive UTC; serialize timezone-aware so browsers in any locale
    # compute correct relative times (was showing "+5h30m" in IST).
    @field_serializer("created_at", "updated_at", "last_active_at")
    def _utc(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()

    class Config:
        from_attributes = True


class WorkspaceList(BaseModel):
    total: int
    items: list[WorkspaceOut]


# ── Sharing ──────────────────────────────────────────────────────────────────

class ShareRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role:     str = Field(default="editor", pattern="^(editor|viewer)$")


class MemberOut(BaseModel):
    user_id:    int
    username:   str
    email:      Optional[str] = None
    avatar_url: Optional[str] = None
    role:       str
    added_at:   datetime

    class Config:
        from_attributes = True


class MemberList(BaseModel):
    total: int
    items: List[MemberOut]


# ── Sharing exclusions + edit history ────────────────────────────────────────

class ExcludesUpdate(BaseModel):
    excludes: List[str] = Field(default_factory=list)


class EditOut(BaseModel):
    username:      str
    path:          str
    lines_added:   int
    lines_removed: int
    created_at:    datetime

    @field_serializer("created_at")
    def _utc(self, v: datetime) -> str:
        from datetime import timezone
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()

    class Config:
        from_attributes = True


# ── Execution ────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    language: str = Field(min_length=1, max_length=32)
    code:     str = Field(min_length=1, max_length=200_000)
    stdin:    Optional[str] = None


class ExecuteResponse(BaseModel):
    language:       str
    exit_code:      int
    stdout:         str
    stderr:         str
    runtime_ms:     int
    timeout:        bool
    truncated:      bool
