"""Pydantic schemas for workspace endpoints."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name:             str  = Field(min_length=1, max_length=128)
    language:         str  = Field(default="python", max_length=32)
    network_access:   bool = False
    filesystem_write: bool = True
    cpu_request:      float = Field(default=0.5, gt=0, le=8)
    memory_request:   int   = Field(default=512, gt=0, le=16384)
    initial_code:     str   = ""


class WorkspaceUpdate(BaseModel):
    name:   Optional[str] = None
    status: Optional[str] = None


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
    created_at:       datetime
    updated_at:       datetime
    last_active_at:   datetime

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
    user_id:  int
    username: str
    role:     str
    added_at: datetime

    class Config:
        from_attributes = True


class MemberList(BaseModel):
    total: int
    items: List[MemberOut]


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
