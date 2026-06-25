"""
Golden-eval — Phase 2 of per-tenant LoRA fine-tuning (tenant-scoped).

Runs the golden case set through the real analysis pipeline and persists a
baseline the operator can later compare a fine-tuned model against. The run hits
the local model many times, so it executes in the background; the baseline file
carries a `status` (running|done|error) the UI polls.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import Tenant
from app.services import eval_runner

router = APIRouter(prefix="/api/tenants/{tenant_id}/eval", tags=["eval"])


@router.get("/baseline")
def get_baseline(
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """The latest saved baseline (with its run status), or status 'none'."""
    return eval_runner.load_baseline(tenant.id) or {"status": "none"}


@router.post("/run", status_code=202)
def run_eval(
    background: BackgroundTasks,
    include_holdout: bool = False,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Kick off a golden-eval run in the background. Poll GET /baseline for the
    result. Synthetic cases always run; the per-tenant holdout is opt-in."""
    tid = tenant.id
    eval_runner.save_baseline(tid, {
        "status": "running",
        "tenant_id": tid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "include_holdout": include_holdout,
    })

    def _task(tenant_id: int, inc: bool) -> None:
        task_db = SessionLocal()
        try:
            report = eval_runner.execute_eval(task_db, tenant_id, include_holdout=inc)
            eval_runner.save_baseline(tenant_id, {"status": "done", **report})
        except Exception as exc:  # noqa: BLE001 — record the failure in the baseline file
            eval_runner.save_baseline(tenant_id, {"status": "error", "error": str(exc),
                                                  "tenant_id": tenant_id})
        finally:
            task_db.close()

    background.add_task(_task, tid, include_holdout)
    return {"status": "started", "include_holdout": include_holdout}
