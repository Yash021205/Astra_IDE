"""
Workspace lifecycle service.

Glues together: risk scoring (sandbox tier), scheduler placement, status
transitions. In production this also calls the Kubernetes API to launch pods
with the chosen runtimeClassName; that path is gated on a live cluster.
"""
from __future__ import annotations
import uuid
from sqlalchemy.orm import Session

from app.models import User, Workspace
from app.schemas.workspace import WorkspaceCreate
from app.services.risk_scorer import RiskScorer, WorkloadRequest, ScoreBreakdown

# Single shared scorer (default cited weights). Swap weights here for an
# ablation deployment — see docs/research/01-adaptive-sandboxing.md.
_scorer = RiskScorer()


def score_workload(req: WorkspaceCreate, user: User) -> ScoreBreakdown:
    """Full breakdown: per-factor subscores + matched escape vectors + tier."""
    return _scorer.score_detailed(WorkloadRequest(
        language=req.language,
        network_access=req.network_access,
        filesystem_write=req.filesystem_write,
        user_trust=user.trust_score,
        code_snippet=req.initial_code or "",
    ))


def compute_risk_score(req: WorkspaceCreate, user: User) -> float:
    """Risk score in [0,1]. Higher = more dangerous = stronger sandbox."""
    return score_workload(req, user).total


def select_sandbox_tier(risk_score: float) -> str:
    """Map a risk score to a sandbox tier (overhead-crossover thresholds)."""
    return _scorer.select_tier(risk_score)


# ── Workspace creation ─────────────────────────────────────────────────────

def create_workspace_for_user(
    db:    Session,
    user:  User,
    req:   WorkspaceCreate,
) -> Workspace:
    breakdown = score_workload(req, user)
    risk = breakdown.total
    # Adaptive (risk-scored) tier by default; honor an explicit manual pin.
    # The risk score is still recorded either way so the UI can show what the
    # adaptive policy WOULD have chosen next to the user's pin.
    tier = req.sandbox_override or breakdown.tier

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

    # Prometheus domain metrics (Monitoring §9): workspace + tier (B4) + scheduler (B1)
    from app.core.metrics import WORKSPACES_CREATED, SANDBOX_TIER, SCHEDULER_DECISIONS
    WORKSPACES_CREATED.inc()
    SANDBOX_TIER.labels(tier).inc()
    SCHEDULER_DECISIONS.labels(decision.algorithm).inc()

    # Build the Pod manifest that ENFORCES the tier (runtimeClassName + hardening).
    # Submitting it needs a live cluster; the manifest itself is built + audited
    # here. See backend/app/services/sandbox_runtime.py and
    # benchmarks/b4_sandboxing/RUNTIME_TESTING.md.
    from app.services import sandbox_runtime
    manifest = sandbox_runtime.manifest_for_workspace(workspace)
    rc = manifest["spec"]["runtimeClassName"]

    # Record the sandbox-tier decision in the activity feed, with the full
    # per-factor breakdown + matched escape vectors (audit trail for the paper).
    from app.services import events_service
    events_service.record(
        kind="sandbox",
        title=f'Sandbox "{tier}" assigned to {req.name}',
        detail=f"{breakdown.explain()} | enforce: runtimeClassName={rc}, "
               f"caps=drop-ALL, seccomp=RuntimeDefault, "
               f"egress={manifest['metadata']['labels']['egress']}",
        workspace_id=workspace.id,
        cluster_id=workspace.cluster_id,
        node_name=workspace.node_name,
    )
    return workspace


def fork_workspace_for_user(db: Session, user: User, src: Workspace) -> Workspace:
    """Create a personal copy of `src` owned by `user` (GitHub-style fork)."""
    fork = Workspace(
        name=f"{src.name}-fork",
        language=src.language,
        status="PENDING",
        sandbox_tier=src.sandbox_tier,
        risk_score=src.risk_score,
        network_access=src.network_access,
        filesystem_write=src.filesystem_write,
        cpu_request=src.cpu_request,
        memory_request=src.memory_request,
        initial_code=src.initial_code,
        forked_from_id=src.id,
        yjs_room=f"ws-{uuid.uuid4().hex[:12]}",          # fresh collab room (independent)
        owner_id=user.id,
        cluster_id=src.cluster_id,
        node_name="",
        pod_name=f"ws-{user.id}-{uuid.uuid4().hex[:8]}",
    )
    db.add(fork)
    db.commit()
    db.refresh(fork)
    return fork


def record_edit(db: Session, workspace_id: int, user: User, path: str,
                old: str, new: str) -> None:
    """Log a file save to the change-history (line diff via difflib)."""
    import difflib
    from app.models import WorkspaceEdit
    added = removed = 0
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    if added == 0 and removed == 0:
        return
    db.add(WorkspaceEdit(
        workspace_id=workspace_id, user_id=user.id, username=user.username,
        path=path, lines_added=added, lines_removed=removed,
    ))
    db.commit()


def get_excludes(ws: Workspace) -> list[str]:
    import json
    try:
        return json.loads(ws.shared_excludes or "[]")
    except (ValueError, TypeError):
        return []


def set_excludes(db: Session, ws: Workspace, paths: list[str]) -> None:
    import json
    ws.shared_excludes = json.dumps(sorted(set(paths)))
    db.commit()


def transition_status(db: Session, workspace: Workspace, new_status: str) -> Workspace:
    previous = workspace.status
    workspace.status = new_status
    db.commit()
    db.refresh(workspace)

    # Starting up → apply the tier-enforcement Pod manifest. Dry-run by default
    # (no cluster in dev); real gVisor/Firecracker launch happens on the cluster
    # when ASTRA_K8S_APPLY=1. The decision is always audited in the activity feed.
    if new_status == "RUNNING" and previous != "RUNNING":
        from app.services import sandbox_runtime, events_service
        res = sandbox_runtime.apply_workspace_pod(workspace)
        events_service.record(
            kind="sandbox",
            title=f'{"Launched" if res.applied else "Planned"} pod {res.pod_name} '
                  f'({res.runtime_class})',
            detail=f"runtimeClassName={res.runtime_class}; {res.reason}",
            workspace_id=workspace.id,
            cluster_id=workspace.cluster_id,
            node_name=workspace.node_name,
        )

    # If the workspace stopped or was archived, release the node slot
    if new_status in ("STOPPED", "ARCHIVED", "FAILED") and previous == "RUNNING":
        from app.services import scheduler_service
        scheduler_service.release_workspace(workspace)
    return workspace
