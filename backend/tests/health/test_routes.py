"""§8 criterion 3: GET /api/v1/health."""


def test_health_returns_200_and_exactly_status_ok(client):
    # No cookie, no X-CSRF-Token header, and no service function is
    # monkeypatched: if the route depended on either it would 401/403 or
    # error instead of answering, so this single call also demonstrates the
    # route is unauthenticated and touches no service (§5.2).
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
