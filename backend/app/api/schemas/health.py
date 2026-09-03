"""Schemas for the health endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload: the process is up and serving requests."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness payload: state of the dependencies the app cannot work without.

    Redis is intentionally absent — a broker outage delays background jobs but
    must not take the HTTP application out of rotation.
    """

    status: Literal["ready", "unavailable"]
    database: Literal["ok", "unavailable"]
