"""Duck-typed stand-ins for `User` and `UserSession` ORM rows.

Not a test module itself (no `test_` prefix - pytest will not collect it).
Used to stub the pinned service functions of `step-0.1.md` §6.1 without a
database: a `SimpleNamespace` exposes the same attributes a real ORM instance
would, and both FastAPI's response serialisation and any `model_validate(...,
from_attributes=True)` call only ever need attribute access, never SQLAlchemy
machinery.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.ids import generate_id

DEFAULT_CSRF_TOKEN = "csrf-token-value"  # noqa: S105 - fixture value, not a secret


def make_user(*, username: str = "aragorn", user_id: str | None = None, created_at=None):
    return SimpleNamespace(
        id=user_id or generate_id(),
        username=username,
        created_at=created_at or datetime.now(UTC),
    )


def make_session(
    *,
    user_id: str,
    csrf_token: str = DEFAULT_CSRF_TOKEN,
    session_id: str | None = None,
    expires_at=None,
):
    return SimpleNamespace(
        id=session_id or generate_id(),
        user_id=user_id,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
