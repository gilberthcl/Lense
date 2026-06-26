"""
Route-registration smoke test.

Guards against the class of bug where an endpoint's @router decorator gets
clobbered (e.g. an edit inserts a sibling route above it), leaving the function
defined but UNREGISTERED → a silent 404/405 in the UI. Asserts the critical
(method, path) pairs the frontend depends on are actually mounted.
"""
from app.main import app

_EXPECTED = {
    # correlation run — regressed once by a decorator clobber (this test exists
    # specifically so that can't happen silently again)
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/correlations/run"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/qa/run"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/qa/rollback"),
    # learning loop
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/findings/{finding_id}/disposition"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/findings/{finding_id}/regenerate"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/findings/missed"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/findings/import"),
    ("POST", "/api/tenants/{tenant_id}/hunts/{hunt_id}/stages/{stage}/feedback"),
    ("GET", "/api/tenants/{tenant_id}/hunts/{hunt_id}/learning-summary"),
    # per-client model
    ("GET", "/api/tenants/{tenant_id}/models/available"),
    ("POST", "/api/tenants/{tenant_id}/models/base"),
    # training data + eval
    ("POST", "/api/tenants/{tenant_id}/training/export"),
    ("POST", "/api/tenants/{tenant_id}/eval/run"),
}


def _mounted() -> set[tuple[str, str]]:
    out = set()
    for r in app.routes:
        for method in getattr(r, "methods", None) or []:
            out.add((method, getattr(r, "path", "")))
    return out


def test_critical_routes_are_registered():
    mounted = _mounted()
    missing = sorted(pair for pair in _EXPECTED if pair not in mounted)
    assert not missing, f"Unregistered endpoints (decorator clobbered?): {missing}"
