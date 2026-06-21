"""Admin API — platform overview of all users, their resources, and which of the
seven breakthroughs each has exercised. Admin-only (User.is_admin)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Workspace, WorkspaceMember, WorkspaceEdit, BenchmarkRun

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


class AdminWorkspace(BaseModel):
    id: int
    name: str
    language: str
    sandbox_tier: str
    status: str
    cpu_cores: Optional[float] = None
    memory_mb: Optional[int] = None
    cluster_id: Optional[str] = None
    risk_score: Optional[float] = None


class AdminUser(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    trust_score: float
    created_at: datetime
    avatar_url: Optional[str] = None
    workspace_count: int
    running_count: int
    tiers: dict           # {runc: n, gvisor: n, firecracker: n}
    total_cpu: float      # sum of requested cores across workspaces
    total_mem_mb: int
    edits: int            # B7/file activity
    shares: int           # B7 collaboration (members on owned workspaces)
    benchmark_runs: int   # B1 benchmark usage
    features: List[str]   # which of the 7 breakthroughs this user has touched
    workspaces: List[AdminWorkspace]


class AdminOverview(BaseModel):
    total_users: int
    total_workspaces: int
    running_workspaces: int
    total_edits: int
    total_benchmark_runs: int
    users: List[AdminUser]


@router.get("/users", response_model=AdminOverview)
def admin_overview(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminOverview:
    users = db.query(User).order_by(User.id.asc()).all()
    out: List[AdminUser] = []
    tot_ws = tot_run = tot_edits = tot_runs = 0

    for u in users:
        wss = db.query(Workspace).filter(Workspace.owner_id == u.id).all()
        tiers = {"runc": 0, "gvisor": 0, "firecracker": 0}
        total_cpu = 0.0
        total_mem = 0
        running = 0
        for w in wss:
            tiers[w.sandbox_tier] = tiers.get(w.sandbox_tier, 0) + 1
            total_cpu += float(getattr(w, "cpu_cores", 0) or 0)
            total_mem += int(getattr(w, "memory_mb", 0) or 0)
            if w.status == "RUNNING":
                running += 1

        ws_ids = [w.id for w in wss]
        edits = (db.query(WorkspaceEdit).filter(WorkspaceEdit.workspace_id.in_(ws_ids)).count()
                 if ws_ids else 0)
        shares = (db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id.in_(ws_ids)).count()
                  if ws_ids else 0)
        runs = db.query(BenchmarkRun).filter(BenchmarkRun.user_id == u.id).count()

        # Which of the 7 breakthroughs this user has actually exercised.
        feats: List[str] = []
        if wss:
            feats.append("B1 scheduler")            # every workspace is PPO-placed
            feats.append("B2 telemetry")            # every running ws emits eBPF telemetry
            feats.append("B4 sandboxing")           # every ws gets a risk-scored tier
        if tiers.get("gvisor") or tiers.get("firecracker"):
            feats.append("B4 hardened tier")
        if shares > 0:
            feats.append("B7 collaboration")
        if running > 0:
            feats.append("B3 prewarming")           # warm-pool eligible
            feats.append("B5 federation")           # placed across clusters
            feats.append("B6 carbon-aware")

        out.append(AdminUser(
            id=u.id, username=u.username, email=u.email,
            is_admin=bool(getattr(u, "is_admin", False)),
            trust_score=u.trust_score, created_at=u.created_at,
            avatar_url=getattr(u, "avatar_url", None),
            workspace_count=len(wss), running_count=running,
            tiers=tiers, total_cpu=round(total_cpu, 1), total_mem_mb=total_mem,
            edits=edits, shares=shares, benchmark_runs=runs,
            features=feats,
            workspaces=[AdminWorkspace(
                id=w.id, name=w.name, language=w.language,
                sandbox_tier=w.sandbox_tier, status=w.status,
                cpu_cores=getattr(w, "cpu_cores", None),
                memory_mb=getattr(w, "memory_mb", None),
                cluster_id=getattr(w, "cluster_id", None),
                risk_score=getattr(w, "risk_score", None),
            ) for w in wss],
        ))
        tot_ws += len(wss); tot_run += running; tot_edits += edits; tot_runs += runs

    return AdminOverview(
        total_users=len(users), total_workspaces=tot_ws, running_workspaces=tot_run,
        total_edits=tot_edits, total_benchmark_runs=tot_runs, users=out,
    )
