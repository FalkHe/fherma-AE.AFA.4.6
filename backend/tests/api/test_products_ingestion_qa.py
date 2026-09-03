"""QA coverage for the enqueue-on-transition ordering (step 2.14), API side.

`test_products.py` already proves the happy path — an enqueue is recorded with
the right `(motorbikeId, operationId)` pair for both `POST /api/products` and
`PATCH status=ingesting` — via the autouse `recorded_enqueues` fixture in
`tests/conftest.py`. What it does not prove is the *ordering* pinned in
`product_service.start_ingestion`'s docstring: "the status change commits, the
`queued` operation row commits … and only then is the task enqueued". This
file makes the enqueue itself fail *after* recording its arguments, and shows
the motorbike/operation rows are already durably committed by that point —
proof the commit-then-enqueue order actually holds, not just that the ids
happen to line up.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.operation import Operation, OperationStatus
from app.db.models.user import UserRole
from app.db.session import get_db_session
from app.services import product_service
from tests.services.conftest import FakeAsyncSession


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def admin_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        registered = client.post(
            "/auth/register", json={"username": "curator", "password": "secret123"}
        )
        assert registered.status_code == 201, registered.text
        assert (
            client.post(
                "/auth/login",
                json={"username": "curator", "password": "secret123", "rememberMe": False},
            ).status_code
            == 200
        )
        fake_session.users[registered.json()["id"]].role = UserRole.ADMIN
        yield client
    api.dependency_overrides.clear()


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _create(client: TestClient, name: str = "Suzuki GSR 600"):
    return client.post(
        "/api/products",
        json={"data": {"type": "products", "attributes": {"name": name}}},
        headers=_csrf(client),
    )


def _patch(client: TestClient, product_id: str, attributes: dict):
    return client.patch(
        f"/api/products/{product_id}",
        json={"data": {"type": "products", "attributes": attributes}},
        headers=_csrf(client),
    )


def _raising_enqueue(calls: list[tuple[str, str]]):
    async def enqueue(motorbike_id: str, operation_id: str) -> None:
        calls.append((motorbike_id, operation_id))
        raise RuntimeError("boom-enqueue")

    return enqueue


def test_create_commits_the_backlog_and_operation_rows_before_enqueue_is_called(
    admin_client: TestClient,
    fake_session: FakeAsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(product_service, "enqueue_ingestion", _raising_enqueue(calls))

    with pytest.raises(RuntimeError, match="boom-enqueue"):
        _create(admin_client)

    # The row and its operation are durably committed despite the enqueue
    # blowing up right after — proof the commit already happened before the
    # `.kiq()` call, not that ids merely happened to be computed in advance.
    motorbikes = fake_session.rows(Motorbike)
    assert len(motorbikes) == 1
    assert motorbikes[0].status is MotorbikeStatus.INGESTING

    operations = fake_session.rows(Operation)
    assert len(operations) == 1
    assert operations[0].type == "ingestion"
    assert operations[0].status is OperationStatus.QUEUED
    assert operations[0].entity_id == motorbikes[0].id

    assert calls == [(motorbikes[0].id, operations[0].id)]


def test_patch_to_ingesting_commits_the_transition_and_operation_before_enqueue(
    admin_client: TestClient,
    fake_session: FakeAsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _create(admin_client).json()["data"]
    for target in ("in_review", "rejected"):
        assert _patch(admin_client, created["id"], {"status": target}).status_code == 200

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(product_service, "enqueue_ingestion", _raising_enqueue(calls))

    with pytest.raises(RuntimeError, match="boom-enqueue"):
        _patch(admin_client, created["id"], {"status": "ingesting"})

    motorbike = next(iter(fake_session.rows(Motorbike)))
    assert motorbike.status is MotorbikeStatus.INGESTING

    # A second `ingestion` operation is now queued for the retry, on top of
    # whatever the initial auto-start created.
    ingestion_operations = [
        operation
        for operation in fake_session.rows(Operation)
        if operation.type == "ingestion" and operation.entity_id == motorbike.id
    ]
    latest = ingestion_operations[-1]
    assert latest.status is OperationStatus.QUEUED
    assert calls == [(motorbike.id, latest.id)]
