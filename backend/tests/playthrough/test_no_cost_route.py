"""WI1 (sprint 005/05b) ← D14: cost has no address. No path this app
serves and no OpenAPI schema field it publishes may carry cost, and asking
the one URL shape someone might guess (`GET .../campaign/{runId}/cost`)
answers `NOT_FOUND` exactly like any other route that does not exist --
FastAPI's own unmatched-route 404, mapped onto this app's error envelope by
`core/errors.py`'s `StarletteHTTPException` handler, not a purpose-built
check in this module.

Only paths and schema *field names* are checked against "cost" -- not
descriptions -- because `EventRead`'s own docstring explains, in prose,
that an event carries no cost on the wire; that sentence mentioning the
word is not the same claim as a field or a path exposing one.
"""

from app.core.ids import generate_id
from app.main import create_app


def test_no_route_path_ever_names_cost():
    app = create_app()

    for route in app.routes:
        path = getattr(route, "path", "")
        assert "cost" not in path.lower(), path


def test_no_openapi_schema_field_ever_names_cost():
    schema = create_app().openapi()

    for name, definition in schema.get("components", {}).get("schemas", {}).items():
        for field in definition.get("properties", {}):
            assert "cost" not in field.lower(), (name, field)


def test_getting_the_guessable_cost_url_answers_not_found(client, assert_error_envelope):
    response = client.get(f"/api/v1/playthrough/campaign/{generate_id()}/cost")
    assert_error_envelope(response, status=404, code="NOT_FOUND")
