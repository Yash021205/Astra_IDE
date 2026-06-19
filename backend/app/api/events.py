"""Activity events API — read-only stream of scheduler / eBPF / sandbox events."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, SchedulerEvent, EVENT_KINDS
from app.schemas.event import EventOut, EventList
from app.services import events_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventList)
def list_events(
    limit: int  = Query(50, ge=1, le=200),
    kind:  str  = Query("", description=f"Filter by kind: one of {EVENT_KINDS}"),
    db:    Session = Depends(get_db),
    _user: User    = Depends(get_current_user),
) -> EventList:
    items = events_service.list_recent(db, limit=limit, kind=kind or None)
    return EventList(total=len(items),
                     items=[EventOut.model_validate(e) for e in items])
