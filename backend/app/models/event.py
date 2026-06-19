"""SchedulerEvent — persistent record of scheduler/eBPF/sandbox events.

These events drive the ActivityFeed on the clusters page. Every time the
scheduler makes a decision, the eBPF telemetry simulator emits a sample,
or a sandbox is assigned, a row is written here.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


# Event kinds map to UI icons + colors (see ActivityFeed.tsx)
EVENT_KINDS = (
    "scheduler",   # PPO placement decision
    "sandbox",     # Sandbox tier assigned
    "ebpf",        # eBPF telemetry tick
    "carbon",      # Carbon intensity update
    "prewarm",     # LSTM prewarming decision
    "collab",      # Collaboration / Yjs event
    "system",      # Service start / shutdown
)


class SchedulerEvent(Base):
    __tablename__ = "scheduler_events"

    id:         Mapped[int]      = mapped_column(primary_key=True, index=True)
    timestamp:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    kind:       Mapped[str]      = mapped_column(String(16))
    title:      Mapped[str]      = mapped_column(String(256))
    detail:     Mapped[str]      = mapped_column(Text, default="")
    workspace_id: Mapped[int]    = mapped_column(Integer, default=0)   # 0 = system event
    cluster_id: Mapped[str]      = mapped_column(String(32), default="")
    node_name:  Mapped[str]      = mapped_column(String(64), default="")


Index("ix_scheduler_events_kind_ts", SchedulerEvent.kind, SchedulerEvent.timestamp.desc())
