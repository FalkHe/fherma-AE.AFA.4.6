"""QA additions to `app/services/product_service.py`.

The dev agent's own `test_product_service.py` already exhaustively parametrizes
the legal/illegal transition matrix, the a2_eligible boundary at 35.0 kW /
ratio 0.2, the full-object spec replace, and the approval side effects. This
file only adds the landed-decision edge cases that file leaves unexercised:

* `DuplicateModelError` carries the slug in `args[0]` (contract pinned in
  shared-knowledge.md `## Landed decisions` → Step 2.1).
* `InvalidTransitionError.__str__` is a ready 422 detail string.
* `a2_eligible` derivation is skipped (returns `None`, not a `ZeroDivisionError`)
  when `wet_weight_kg <= 0` — a guard named in the same Landed-decisions entry
  but not covered by the pinned boundary-value table.
* `rejected` retains source documents, not just the draft spec and images
  (the dev file only asserted spec/image retention).
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.models.motorbike import MotorbikeStatus
from app.db.models.source_document import SourceType
from app.services import document_service, product_service
from app.services.product_service import DuplicateModelError, InvalidTransitionError
from tests.services.conftest import FakeAsyncSession


def test_duplicate_model_error_carries_the_slug(fake_session: FakeAsyncSession) -> None:
    asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    with pytest.raises(DuplicateModelError) as raised:
        asyncio.run(product_service.create_backlog(fake_session, "suzuki gsr-600"))

    assert raised.value.args[0] == "suzuki-gsr-600"


def test_invalid_transition_error_str_is_a_ready_422_detail() -> None:
    error = InvalidTransitionError(MotorbikeStatus.APPROVED, MotorbikeStatus.BACKLOG)

    assert str(error) == "Cannot change status from 'approved' to 'backlog'."
    assert error.current is MotorbikeStatus.APPROVED
    assert error.requested is MotorbikeStatus.BACKLOG


@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("-10.0")])
def test_a2_eligible_not_derivable_when_weight_is_not_positive(
    fake_session: FakeAsyncSession, weight: Decimal
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    spec = asyncio.run(
        product_service.upsert_draft_spec(
            fake_session,
            motorbike.id,
            {"power_kw": Decimal("20.0"), "wet_weight_kg": weight},
        )
    )

    assert spec.a2_eligible is None


def test_rejection_retains_source_documents(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    motorbike.status = MotorbikeStatus.IN_REVIEW
    document = asyncio.run(
        document_service.create_document(
            fake_session,
            motorbike.id,
            source_type=SourceType.WIKIPEDIA,
            source_title="Suzuki GSR600",
            raw_path=f"sources/{motorbike.id}/doc.html",
            content_markdown="# Suzuki GSR600",
            fetched_at=datetime(2026, 8, 26, 10, tzinfo=UTC),
        )
    )

    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.REJECTED))

    remaining = asyncio.run(document_service.list_for_motorbike(fake_session, motorbike.id))
    assert remaining == [document]
