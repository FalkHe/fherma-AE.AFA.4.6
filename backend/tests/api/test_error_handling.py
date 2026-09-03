"""Tests for the global 500 catch-all handler (`app.main.unhandled_exception_handler`).

`/ready` is reused as the forcing route: `is_database_reachable` only catches
`SQLAlchemyError`, so a bare exception raised by the stub session's `execute`
propagates unhandled all the way to the app-level handler, exactly like a real
bug would. No route is monkeypatched directly — the outline's intent (a route
that raises) is satisfied without adding a new endpoint or reaching into
route internals.
"""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import StubSession


def test_unhandled_exception_returns_generic_jsonapi_500(
    api: FastAPI,
    stub_db_session: Callable[..., StubSession],
) -> None:
    """A bare exception anywhere in the stack renders the generic envelope."""
    stub_db_session(RuntimeError("password=hunter2 leaked from a traceback"))

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get("/ready")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "errors": [
            {
                "status": "500",
                "code": "internal-error",
                "detail": body["errors"][0]["detail"],
            }
        ]
    }
    detail = body["errors"][0]["detail"]
    assert "RuntimeError" not in detail
    assert "hunter2" not in detail
    assert "password" not in detail.lower()


def test_existing_422_validation_shape_is_unchanged(
    client: TestClient,
    stub_db_session: Callable[..., StubSession],
) -> None:
    """Request-body validation still keeps FastAPI's default `detail` list shape."""
    stub_db_session()

    response = client.post("/auth/register", json={"username": "validname", "password": "short12"})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "password") in locs
