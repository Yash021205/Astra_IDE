"""Event logging — records SchedulerEvent rows for the activity feed."""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import SchedulerEvent


def record(
    kind:         str,
    title:        str,
    detail:       str = "",
    workspace_id: int = 0,
    cluster_id:   str = "",
    node_name:    str = "",
    db:           Optional[Session] = None,
) -> SchedulerEvent:
    """
    Insert one SchedulerEvent row. If no db session is passed, opens its own
    short-lived session — useful for background tasks that don't have a
    request-scoped session available.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    assert db is not None
    try:
        ev = SchedulerEvent(
            kind=kind, title=title, detail=detail,
            workspace_id=workspace_id, cluster_id=cluster_id, node_name=node_name,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev
    finally:
        if own_session:
            db.close()


def list_recent(
    db:    Session,
    limit: int = 50,
    kind:  Optional[str] = None,
) -> List[SchedulerEvent]:
    q = db.query(SchedulerEvent)
    if kind:
        q = q.filter(SchedulerEvent.kind == kind)
    return q.order_by(SchedulerEvent.timestamp.desc()).limit(limit).all()


def prune_old(db: Session, keep_last: int = 500) -> int:
    """Keep only the most recent N events (the feed table grows fast)."""
    rows = (
        db.query(SchedulerEvent.id)
        .order_by(SchedulerEvent.timestamp.desc())
        .offset(keep_last)
        .all()
    )
    if not rows:
        return 0
    ids = [r[0] for r in rows]
    deleted = (
        db.query(SchedulerEvent)
        .filter(SchedulerEvent.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
