"""Tests for `app/main.py` (`create_app()`), mirroring it at the top level of
the tree the way `app/main.py` sits at the top level of `app/`.

Covers criterion 4 (`/docs` renders in the default `development`
configuration) and a security-relevant edge case §6.1 pins but §8 does not
number outright: `/docs` and `/openapi.json` must be disabled in
`production`, while `app.openapi()` - what the CLI's `openapi export` depends
on - keeps working regardless.
"""


def test_docs_and_openapi_json_are_served_in_development(client):
    docs = client.get("/docs")
    openapi_json = client.get("/openapi.json")

    assert docs.status_code == 200
    assert openapi_json.status_code == 200


def test_docs_and_openapi_json_are_disabled_in_production(production_client):
    docs = production_client.get("/docs")
    openapi_json = production_client.get("/openapi.json")

    assert docs.status_code == 404
    assert openapi_json.status_code == 404


def test_openapi_document_is_still_available_via_the_python_api_in_production(production_client):
    # `app openapi export` calls `create_app().openapi()` directly (§6.1),
    # never the HTTP route, so it must keep working even though the `/docs`
    # and `/openapi.json` HTTP routes are switched off.
    schema = production_client.app.openapi()

    assert "/api/v1/health" in schema["paths"]
