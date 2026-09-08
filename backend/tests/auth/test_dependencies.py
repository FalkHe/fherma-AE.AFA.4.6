"""Contract test for `app.modules.auth.dependencies.require_auth` (§6.1,
`shared-knowledge.md` D19): exactly two service calls, in this order -
`auth.service.resolve_session` then `users.service.get_user_by_id`. Driven
through a protected route (GET /users/me) rather than by calling the
dependency directly, per the suite's synchronous-only arrangement (§6.5).
"""

import uuid

from app.modules.auth import service as auth_service
from app.modules.users import service as users_service
from tests.factories import make_session, make_user


def test_require_auth_calls_resolve_session_then_get_user_by_id_in_that_order(
    client, monkeypatch, session_cookie_header
):
    user_id = uuid.uuid4()
    call_order: list[str] = []

    async def fake_resolve_session(db, *, token):
        call_order.append("resolve_session")
        return make_session(user_id=user_id)

    async def fake_get_user_by_id(db, *, user_id):
        call_order.append("get_user_by_id")
        return make_user(user_id=user_id)

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

    response = client.get("/api/v1/users/me", headers=session_cookie_header("a-valid-cookie"))

    assert response.status_code == 200
    assert call_order == ["resolve_session", "get_user_by_id"]
