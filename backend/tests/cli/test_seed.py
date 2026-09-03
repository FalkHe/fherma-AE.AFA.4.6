"""Tests for `app seed demo` (step 5.11).

Per the 2.19 precedent, a CLI command that drives the real ingestion pipeline
gets no test for its live path (that needs the real internet and an LLM) —
these tests prove the orchestration instead: skip-if-exists, report-and-
continue, `--auto-approve` going through the real transition service, and the
exit-code rule. `product_service.start_ingestion` is stubbed to resolve
immediately to a terminal operation (`succeeded`/`failed`), so `_poll` never
actually loops or sleeps; `get_sessionmaker` points at the same in-memory
`FakeAsyncSession` other CLI tests use (`tests/services/conftest.py`), so the
real skip/transition logic runs end to end without a database or an event
loop of our own. The broker is stubbed exactly as `tests/cli/test_jobs.py`
does, since `app seed demo` opens and closes a connection around the whole run
regardless of whether any model reaches the real enqueue.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli import seed as seed_cli
from app.cli.main import app as cli
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.services import operation_service, product_service
from tests.services.conftest import FakeAsyncSession

runner = CliRunner()


class _SessionContextManager:
    """Adapts a `FakeAsyncSession` to the `async with sessionmaker() as s:` shape."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeAsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _StubBroker:
    """Counts the broker's connection lifecycle calls; never touches Redis."""

    def __init__(self) -> None:
        self.startups = 0
        self.shutdowns = 0

    async def startup(self) -> None:
        self.startups += 1

    async def shutdown(self) -> None:
        self.shutdowns += 1


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture(autouse=True)
def _patch_sessionmaker(monkeypatch: pytest.MonkeyPatch, fake_session: FakeAsyncSession) -> None:
    monkeypatch.setattr(
        "app.cli.seed.get_sessionmaker",
        lambda: lambda: _SessionContextManager(fake_session),
    )


@pytest.fixture(autouse=True)
def stub_broker(monkeypatch: pytest.MonkeyPatch) -> _StubBroker:
    stub = _StubBroker()
    monkeypatch.setattr("app.cli.seed.broker", stub)
    return stub


@pytest.fixture
def seed_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Point the command at a small, test-owned list instead of the real one.

    Decouples these tests from the curated production model list, which may
    change independently of this orchestration contract.
    """
    names = ["Kawasaki Z400", "KTM 390 Duke"]
    path = tmp_path / "seed_models.json"
    path.write_text(json.dumps([{"name": name} for name in names]))
    monkeypatch.setattr(seed_cli, "SEED_MODELS_PATH", path)
    return names


async def _stub_start_ingestion_success(session: Any, motorbike: Any) -> Any:
    """Stand in for a worker run that ingests a model successfully."""
    operation = await operation_service.create(
        session,
        product_service.INGESTION_OPERATION_TYPE,
        entity_type=operation_service.MOTORBIKE_ENTITY_TYPE,
        entity_id=motorbike.id,
    )
    await product_service.transition(session, motorbike, MotorbikeStatus.INGESTING)
    await product_service.transition(session, motorbike, MotorbikeStatus.IN_REVIEW)
    return await operation_service.succeed(session, operation)


async def _stub_start_ingestion_success_with_identity(session: Any, motorbike: Any) -> Any:
    """`_stub_start_ingestion_success`, plus a filled identity block.

    Sets the three D4-guarded fields directly (bypassing `assign_identity` on
    purpose — this is test setup standing in for a future post-6.15 extraction
    run, not a production write path), so the `--auto-approve` happy path stays
    testable even though today's real ingestion does not fill identity yet.
    """
    operation = await _stub_start_ingestion_success(session, motorbike)
    motorbike.manufacturer_id = "01SEEDMANUFACTUREREXAMPL0"
    motorbike.model_name = motorbike.query_name
    motorbike.year_from = 2020
    return operation


def _stub_start_ingestion_failure(error: str) -> Any:
    """Build a stand-in for a worker run that fails with `error`."""

    async def _stub(session: Any, motorbike: Any) -> Any:
        operation = await operation_service.create(
            session,
            product_service.INGESTION_OPERATION_TYPE,
            entity_type=operation_service.MOTORBIKE_ENTITY_TYPE,
            entity_id=motorbike.id,
        )
        await product_service.transition(session, motorbike, MotorbikeStatus.INGESTING)
        await product_service.transition(session, motorbike, MotorbikeStatus.BACKLOG)
        return await operation_service.fail(session, operation, error)

    return _stub


# --- skip-if-exists ------------------------------------------------------------


def test_a_model_whose_slug_already_exists_in_any_status_is_skipped(
    fake_session: FakeAsyncSession,
    seed_list: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingested: list[str] = []

    async def _record_and_succeed(session: Any, motorbike: Any) -> Any:
        ingested.append(motorbike.query_name)
        return await _stub_start_ingestion_success(session, motorbike)

    async def _seed_existing() -> None:
        motorbike = await product_service.create_backlog(fake_session, seed_list[0])
        motorbike.status = MotorbikeStatus.REJECTED

    asyncio.run(_seed_existing())
    monkeypatch.setattr(product_service, "start_ingestion", _record_and_succeed)

    result = runner.invoke(cli, ["seed", "demo"])

    assert result.exit_code == 0, result.output
    assert f"{seed_list[0]}: skipped (exists: rejected)" in result.stdout
    assert seed_list[0] not in ingested
    assert seed_list[1] in ingested
    assert "Summary:" in result.stdout
    assert "1 skipped" in result.stdout


def test_all_models_skipped_is_not_a_failure(
    fake_session: FakeAsyncSession, seed_list: list[str]
) -> None:
    async def _seed_all() -> None:
        for name in seed_list:
            await product_service.create_backlog(fake_session, name)

    asyncio.run(_seed_all())

    result = runner.invoke(cli, ["seed", "demo"])

    assert result.exit_code == 0, result.output
    assert result.stdout.count("skipped (exists: backlog)") == len(seed_list)


# --- report-and-continue --------------------------------------------------------


def test_a_failing_model_is_reported_and_the_run_continues(
    fake_session: FakeAsyncSession, seed_list: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        product_service, "start_ingestion", _stub_start_ingestion_failure("boom: search failed")
    )

    result = runner.invoke(cli, ["seed", "demo"])

    assert result.exit_code == 1, result.output
    for name in seed_list:
        assert f"{name}: failed (boom: search failed)" in result.stdout
    assert "2 failed" in result.stdout


def test_one_failure_and_one_success_exits_zero(
    fake_session: FakeAsyncSession, seed_list: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}

    async def _alternating(session: Any, motorbike: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 1:
            return await _stub_start_ingestion_failure("boom")(session, motorbike)
        return await _stub_start_ingestion_success(session, motorbike)

    monkeypatch.setattr(product_service, "start_ingestion", _alternating)

    result = runner.invoke(cli, ["seed", "demo"])

    assert result.exit_code == 0, result.output
    assert f"{seed_list[0]}: failed (boom)" in result.stdout
    assert f"{seed_list[1]}: seeded" in result.stdout
    assert "1 seeded, 0 approved, 0 skipped, 1 failed." in result.stdout


# --- --auto-approve --------------------------------------------------------------


def test_auto_approve_calls_the_transition_service_on_success(
    fake_session: FakeAsyncSession, seed_list: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        product_service, "start_ingestion", _stub_start_ingestion_success_with_identity
    )

    result = runner.invoke(cli, ["seed", "demo", "--auto-approve"])

    assert result.exit_code == 0, result.output
    for name in seed_list:
        assert f"{name}: approved" in result.stdout
    assert "0 seeded, 2 approved, 0 skipped, 0 failed." in result.stdout
    statuses = {
        motorbike.query_name: motorbike.status for motorbike in fake_session.rows(Motorbike)
    }
    assert statuses == dict.fromkeys(seed_list, MotorbikeStatus.APPROVED)


def test_auto_approve_reports_an_incomplete_identity_as_a_failure(
    fake_session: FakeAsyncSession, seed_list: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4 (step 6.12): a successful ingestion with no identity yet cannot be
    auto-approved — `transition` raises `IncompleteIdentityError`, and the
    command reports it the same way it reports an ingestion failure (report-
    and-continue), rather than crashing the run.
    """
    monkeypatch.setattr(product_service, "start_ingestion", _stub_start_ingestion_success)

    result = runner.invoke(cli, ["seed", "demo", "--auto-approve"])

    assert result.exit_code == 1, result.output
    for name in seed_list:
        assert f"{name}: failed (" in result.stdout
        assert "incomplete" in result.stdout
    assert "0 seeded, 0 approved, 0 skipped, 2 failed." in result.stdout
    statuses = {
        motorbike.query_name: motorbike.status for motorbike in fake_session.rows(Motorbike)
    }
    assert statuses == dict.fromkeys(seed_list, MotorbikeStatus.IN_REVIEW)


def test_auto_approve_is_not_applied_to_a_failed_model(
    fake_session: FakeAsyncSession, seed_list: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(product_service, "start_ingestion", _stub_start_ingestion_failure("boom"))

    result = runner.invoke(cli, ["seed", "demo", "--auto-approve"])

    assert result.exit_code == 1, result.output
    statuses = {
        motorbike.query_name: motorbike.status for motorbike in fake_session.rows(Motorbike)
    }
    assert statuses == dict.fromkeys(seed_list, MotorbikeStatus.BACKLOG)
