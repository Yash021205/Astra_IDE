"""
Workspace lifecycle service.

Glues together: risk scoring (sandbox tier), pod naming, status transitions.
In production this would also call the Kubernetes API to actually launch pods;
for now those calls are mocked to keep the dev loop fast.
"""
from __future__ import annotations
import uuid
from sqlalchemy.orm import Session

from app.models import User, Workspace
from app.schemas.workspace import WorkspaceCreate


# ── Risk scorer (mirrors logic in ml/risk_scorer) ───────────────────────────
# Kept duplicated here so the backend can score without importing the ML package
# (which keeps the backend container slim). Both implementations must stay in sync;
# the ml/risk_scorer is the canonical version for offline experimentation.

_DANGEROUS_LANGS = {"bash", "sh", "shell", "powershell"}


def compute_risk_score(req: WorkspaceCreate, user: User) -> float:
    """
    Returns a risk score in [0, 1].
    Higher score → more dangerous → stronger sandbox needed.
    """
    score = 0.0
    if req.language.lower() in _DANGEROUS_LANGS:
        score += 0.30
    if req.network_access:
        score += 0.20
    if req.filesystem_write:
        score += 0.20
    if user.trust_score < 0.5:
        score += 0.20
    if _contains_suspicious_keywords(req.initial_code):
        score += 0.10
    return min(score, 1.0)


def select_sandbox_tier(risk_score: float) -> str:
    """Map risk score to sandbox tier."""
    if risk_score < 0.30:
        return "runc"
    if risk_score < 0.70:
        return "gvisor"
    return "firecracker"


_SUSPICIOUS_KEYWORDS = (
    "subprocess", "os.system", "eval(", "exec(",
    "/dev/", "mount ", "chmod 777", "rm -rf /",
    "iptables", "raw socket",
)


def _contains_suspicious_keywords(code: str) -> bool:
    lowered = code.lower()
    return any(kw in lowered for kw in _SUSPICIOUS_KEYWORDS)


# ── Workspace creation ─────────────────────────────────────────────────────

def create_workspace_for_user(
    db:    Session,
    user:  User,
    req:   WorkspaceCreate,
) -> Workspace:
    risk = compute_risk_score(req, user)
    tier = select_sandbox_tier(risk)

    workspace = Workspace(
        name=req.name,
        language=req.language,
        status="PENDING",
        sandbox_tier=tier,
        risk_score=risk,
        network_access=req.network_access,
        filesystem_write=req.filesystem_write,
        cpu_request=req.cpu_request,
        memory_request=req.memory_request,
        initial_code=req.initial_code,
        yjs_room=f"ws-{uuid.uuid4().hex[:12]}",
        owner_id=user.id,
        cluster_id="cluster-a",         # filled in by scheduler immediately below
        node_name="",
        pod_name=f"ws-{user.id}-{uuid.uuid4().hex[:8]}",
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    # Ask the scheduler where to place this workspace — picks cluster + node
    # based on current cluster_state telemetry + carbon intensity.
    from app.services import scheduler_service           # local import avoids cycle
    decision = scheduler_service.decide_placement(workspace)
    workspace.cluster_id = decision.cluster_id
    workspace.node_name  = decision.node_name
    db.commit()
    db.refresh(workspace)

    # Record the sandbox-tier decision in the activity feed
    from app.services import events_service
    events_service.record(
        kind="sandbox",
        title=f'Sandbox "{tier}" assigned to {req.name}',
        detail=f"risk={risk:.2f} | language={req.language} | "
               f"network={req.network_access} | fs_write={req.filesystem_write}",
        workspace_id=workspace.id,
        cluster_id=workspace.cluster_id,
        node_name=workspace.node_name,
    )
    return workspace


def transition_status(db: Session, workspace: Workspace, new_status: str) -> Workspace:
    previous = workspace.status
    workspace.status = new_status
    db.commit()
    db.refresh(workspace)

    # If the workspace stopped or was archived, release the node slot
    if new_status in ("STOPPED", "ARCHIVED", "FAILED") and previous == "RUNNING":
        from app.services import scheduler_service
        scheduler_service.release_workspace(workspace)
    return workspace
