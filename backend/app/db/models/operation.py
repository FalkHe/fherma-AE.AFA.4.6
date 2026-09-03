"""The `operations` table: one row per tracked long-running job."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

TYPE_LENGTH = 64
MESSAGE_LENGTH = 512
ERROR_LENGTH = 2048
ENTITY_TYPE_LENGTH = 32

# Progress is a percentage; the column has no CHECK constraint, so the service
# is where an out-of-range value is caught.
MIN_PROGRESS = 0
MAX_PROGRESS = 100


class OperationStatus(StrEnum):
    """Lifecycle position of an operation.

    `queued` → `running` → `succeeded` | `failed`; the terminal states are
    final. Progress and message are advisory, the status is authoritative.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Operation(ULIDPrimaryKeyMixin, Base):
    """Progress of one background job, as the admin UI sees it.

    This table — not the task queue — is the state of a job: the broker has no
    result backend, so a row here is what survives a worker restart.

    `entity_type` / `entity_id` are a deliberately loose link (no foreign key):
    an operation may outlive the row it worked on, and the pair is only ever
    used to look operations up for a screen. `message` is English prose shown
    verbatim in the admin UI.
    """

    __tablename__ = "operations"

    # The admin backlog looks operations up by the entity they belong to.
    __table_args__ = (Index(None, "entity_type", "entity_id"),)

    # Job family, e.g. 'ingestion', 'embeddings.rebuild', 'demo'. Free text
    # rather than an enum: the set grows with every new job module.
    type: Mapped[str] = mapped_column(String(TYPE_LENGTH))
    status: Mapped[OperationStatus] = mapped_column(
        # Native PostgreSQL enum carrying the member *values* (see `User.role`).
        Enum(
            OperationStatus,
            name="operation_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        server_default=OperationStatus.QUEUED.value,
    )
    progress: Mapped[int] = mapped_column(SmallInteger, server_default=str(MIN_PROGRESS))
    # Current step, NULL until the job reports one.
    message: Mapped[str | None] = mapped_column(String(MESSAGE_LENGTH))
    # Set only by a failure; kept when the job is retried by a fresh operation.
    error: Mapped[str | None] = mapped_column(String(ERROR_LENGTH))
    entity_type: Mapped[str | None] = mapped_column(String(ENTITY_TYPE_LENGTH))
    entity_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL while queued / while unfinished.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
