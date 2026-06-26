"""
Reusable tenant-isolation assertion (W0).

The hard rule: no service may ever return another tenant's rows. Import
`assert_tenant_scoped` in any test that exercises a tenant-scoped query and feed
it the rows — it fails loudly on the first cross-tenant leak.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable


def assert_tenant_scoped(
    rows: Iterable[Any],
    tenant_id: int,
    *,
    get_tid: Callable[[Any], int] = lambda r: r.tenant_id,
    label: str = "result set",
) -> None:
    leaked = [r for r in rows if get_tid(r) != tenant_id]
    assert not leaked, (
        f"Tenant isolation breach in {label}: {len(leaked)} row(s) belong to "
        f"another tenant (expected only tenant {tenant_id})."
    )
