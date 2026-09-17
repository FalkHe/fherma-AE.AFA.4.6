from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import ID_TYPE, generate_id


class CampaignRun(Base):
    """One player's playthrough of a campaign: the content it was started
    from, its lifecycle status and the model settings it runs with.
    Ownership lives in `CampaignRunMember`, not here."""

    __tablename__ = "campaign_runs"
    __table_args__ = (CheckConstraint("status IN ('active','archived','finished')", name="status"),)

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    campaign_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_version: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    personality_prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CampaignRunMember(Base):
    """A user's membership in a campaign run. Today the only role is
    `owner` and every run has exactly one member; the table exists ahead of
    multi-member runs so that ownership never lives on `CampaignRun`."""

    __tablename__ = "campaign_run_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner')", name="role"),
        UniqueConstraint(
            "campaign_run_id", "user_id", name="uq_campaign_run_members_campaign_run_id"
        ),
    )

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    campaign_run_id: Mapped[str] = mapped_column(
        ID_TYPE, ForeignKey("campaign_runs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdventureRun(Base):
    """One adventure entered within a campaign run. `status` tracks whether
    it is the one currently in progress (`active`) or has been played to
    completion (`completed`); a run may have at most one `active` adventure
    at a time, and `completed_at` is set if and only if `status` is
    `completed`. No scene/position column here -- that belongs to the
    creature, not the adventure, and lands in a later sprint."""

    __tablename__ = "adventure_runs"
    __table_args__ = (
        UniqueConstraint(
            "campaign_run_id", "adventure_id", name="uq_adventure_runs_campaign_run_id"
        ),
        CheckConstraint("status IN ('active','completed')", name="status"),
        CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at"),
        Index(
            "uq_adventure_runs_active",
            "campaign_run_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    campaign_run_id: Mapped[str] = mapped_column(
        ID_TYPE, ForeignKey("campaign_runs.id", ondelete="CASCADE"), nullable=False
    )
    adventure_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
