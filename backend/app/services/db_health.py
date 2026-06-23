"""
Database / storage health & cleanup.

The main source of "mess" is orphaned files: deleting a hunt or dataset cascades
the DB rows away but leaves the uploaded CSVs/logos on disk. This module scans
for that (and other inconsistencies) and can clean it up safely.

scan() is read-only. clean() deletes orphaned files and clears stuck jobs.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AnalysisJob, Dataset, Finding, Hunt, Tenant
from app.services import global_config, jobs

UPLOAD_ROOT = Path("uploads")


def _resolve(p: str | Path) -> str:
    try:
        return str(Path(p).resolve())
    except Exception:  # noqa: BLE001
        return str(p)


def _referenced_paths(db: Session) -> set[str]:
    """Every file path the database currently points to."""
    refs: set[str] = set()
    for (fp,) in db.query(Dataset.file_path).all():
        if fp:
            refs.add(_resolve(fp))
    for logo, contract in db.query(Tenant.logo_path, Tenant.contract_path).all():
        if logo:
            refs.add(_resolve(logo))
        if contract:
            refs.add(_resolve(contract))
    platform_logo = global_config.get_platform(db).get("logo_path")
    if platform_logo:
        refs.add(_resolve(platform_logo))
    return refs


def find_orphan_files(root: Path, referenced: set[str]) -> list[Path]:
    """Files under `root` not referenced by the database (pure / testable)."""
    if not root.exists():
        return []
    orphans: list[Path] = []
    for f in root.rglob("*"):
        if f.is_file() and _resolve(f) not in referenced:
            orphans.append(f)
    return orphans


def scan(db: Session) -> dict:
    referenced = _referenced_paths(db)
    orphans = find_orphan_files(UPLOAD_ROOT, referenced)
    orphan_bytes = sum((f.stat().st_size for f in orphans), 0)

    missing = [
        {"id": d.id, "filename": d.filename, "path": d.file_path}
        for d in db.query(Dataset).all()
        if not Path(d.file_path).exists()
    ]
    stuck = [
        {"id": j.id, "phase": j.phase, "status": j.status, "hunt_id": j.hunt_id}
        for j in db.query(AnalysisJob).filter(AnalysisJob.status.in_(jobs.ACTIVE)).all()
    ]

    return {
        "counts": {
            "clients": db.query(Tenant).count(),
            "hunts": db.query(Hunt).count(),
            "datasets": db.query(Dataset).count(),
            "findings": db.query(Finding).count(),
            "jobs": db.query(AnalysisJob).count(),
        },
        "orphan_files": {
            "count": len(orphans),
            "bytes": orphan_bytes,
            "sample": [str(f) for f in orphans[:20]],
        },
        "missing_dataset_files": missing,
        "stuck_jobs": stuck,
        "healthy": not orphans and not missing and not stuck,
    }


def clean(db: Session) -> dict:
    """Delete orphaned files and clear stuck jobs. Returns what was done."""
    referenced = _referenced_paths(db)
    orphans = find_orphan_files(UPLOAD_ROOT, referenced)
    removed, freed = 0, 0
    for f in orphans:
        try:
            size = f.stat().st_size
            f.unlink()
            removed += 1
            freed += size
        except Exception:  # noqa: BLE001 — skip files we can't remove
            continue

    cleared = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.status.in_(jobs.ACTIVE))
        .update(
            {"status": "error", "error": "cleared by maintenance"},
            synchronize_session=False,
        )
    )
    db.commit()

    # Remove now-empty directories under uploads/.
    if UPLOAD_ROOT.exists():
        for d in sorted(UPLOAD_ROOT.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                try:
                    d.rmdir()
                except Exception:  # noqa: BLE001
                    pass

    return {"removed_files": removed, "freed_bytes": freed, "cleared_jobs": cleared}
