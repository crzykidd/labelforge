"""Smoke test: the app must import and build its OpenAPI schema.

Catches import-time / route-registration failures that per-module unit tests miss —
e.g. an invalid FastAPI `response_model` (a return annotation unioning a Response type)
raises when the route is registered, taking the whole app down at startup while every
isolated unit test stays green. CI had no such guard before this test.
"""


def test_app_imports_and_core_routes_registered():
    from labelforge.main import app

    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/printer/status" in paths


def test_openapi_schema_builds():
    # Generating the schema exercises response-model construction for every route;
    # an invalid return annotation raises here rather than only at container startup.
    from labelforge.main import app

    schema = app.openapi()
    assert schema["info"]["title"]
