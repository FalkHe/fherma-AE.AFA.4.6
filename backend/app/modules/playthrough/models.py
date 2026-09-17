from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class GameObject(Base):
    """A creature, item or fixture instantiated within a campaign run
    (`__tablename__ = "objects"`; named `GameObject` because `Object` shadows
    a builtin). `source_adventure_id`/`source_scene_id` are provenance,
    written once at instantiation; `adventure_run_id`/`scene_id` are
    position, written on entry and every move -- the two pairs are
    deliberately unconstrained against each other. A thing with an owner
    (carried) never also has a position, and position is always both
    columns or neither. The four fighting stats (`current_hp`, `max_hp`,
    `armour_class`, `is_alive`) exist if and only if `kind` is `creature`.
    No ORM relationship."""

    __tablename__ = "objects"
    __table_args__ = (
        UniqueConstraint("campaign_run_id", "instance_key", name="uq_objects_campaign_run_id"),
        CheckConstraint("kind IN ('creature','item','fixture')", name="kind"),
        CheckConstraint(
            "(kind = 'creature') = (current_hp IS NOT NULL) AND "
            "(kind = 'creature') = (max_hp IS NOT NULL) AND "
            "(kind = 'creature') = (armour_class IS NOT NULL) AND "
            "(kind = 'creature') = (is_alive IS NOT NULL)",
            name="stats_creature_only",
        ),
        CheckConstraint(
            "(current_hp IS NULL AND max_hp IS NULL) OR "
            "(current_hp IS NOT NULL AND max_hp IS NOT NULL AND "
            "current_hp >= 0 AND current_hp <= max_hp)",
            name="hp_range",
        ),
        CheckConstraint("(adventure_run_id IS NULL) = (scene_id IS NULL)", name="position"),
        CheckConstraint(
            "owner_object_id IS NULL OR (adventure_run_id IS NULL AND scene_id IS NULL)",
            name="carried",
        ),
        Index("ix_objects_adventure_run_id_scene_id", "adventure_run_id", "scene_id"),
    )

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    campaign_run_id: Mapped[str] = mapped_column(
        ID_TYPE, ForeignKey("campaign_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[str | None] = mapped_column(
        ID_TYPE,
        ForeignKey("campaign_run_members.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    instance_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_adventure_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adventure_run_id: Mapped[str | None] = mapped_column(
        ID_TYPE, ForeignKey("adventure_runs.id", ondelete="SET NULL"), nullable=True
    )
    scene_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_object_id: Mapped[str | None] = mapped_column(
        ID_TYPE, ForeignKey("objects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    current_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    armour_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_alive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
