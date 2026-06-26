"""
Reconstruct tenants / hunts / datasets from the surviving `uploads/` tree.

Context: the original Postgres lived in a Docker volume that was deleted when
Docker was removed from this machine. The DB *records* are gone, but the raw
uploaded files survived on disk under backend/uploads/:

    uploads/tenant_<id>/logo_<...>            ← client logo
    uploads/tenant_<id>/hunt_<id>/<hash>_<name>.csv   ← datasets

This rebuilds the DB rows that point at those files, with their ORIGINAL ids
(so file paths and any bookmarks line up), and resets each dataset to
'uploaded' so analysis can be re-run. Idempotent: re-running skips rows that
already exist.

What it canNOT recover (gone with the DB): client display names, hunt titles,
methodology text, and the previously-generated findings. Names are guessed from
the logo filenames; edit NAME_OVERRIDES / HUNT_NAMES below or rename in the UI.
Methodology must be re-attached and analysis re-run (findings regenerate).

Run from the backend dir with the venv active:
    cd backend && source venv/bin/activate && python scripts/recover_from_uploads.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Make `app` importable when run as `python scripts/recover_from_uploads.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.models import Dataset, Hunt, Tenant  # noqa: E402
from app.services import csv_loader  # noqa: E402

UPLOAD_ROOT = Path("uploads")
HASH_PREFIX = re.compile(r"^[0-9a-f]{32}_")

# Best-effort client names inferred from the surviving logo filenames. Edit
# these (or rename later in the UI) — only YOU know the real names.
NAME_OVERRIDES: dict[int, str] = {
    1: "Client 1 (rename me)",
    2: "Client 2 (rename me)",
    3: "Client 3 (rename me)",
    4: "Client 4 (rename me)",
}
# Optional human titles for known hunts; otherwise a placeholder is used.
HUNT_NAMES: dict[int, str] = {
    5: "ROPC Threat Hunt (recovered)",
    6: "ROPC Threat Hunt (recovered)",
}


def _slugify(name: str, tid: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"tenant-{tid}"


def _clean_filename(disk_name: str) -> str:
    """Strip the uuid hash prefix the uploader prepended, recovering the name."""
    return HASH_PREFIX.sub("", disk_name)


def _dataset_meta(path: Path) -> tuple[int, int, list[dict] | None]:
    try:
        df = csv_loader.load_csv(path, 64 * 1024 * 1024)
        return int(df.shape[0]), int(df.shape[1]), [{"name": str(c)} for c in df.columns]
    except Exception as exc:  # noqa: BLE001 — metadata is best-effort
        print(f"      ! could not read {path.name}: {exc}")
        return 0, 0, None


def _reset_sequences(db) -> None:
    """After explicit-id inserts, bump each id sequence past the max id."""
    for table in ("tenants", "hunts", "datasets"):
        db.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
        ))


def main() -> int:
    if not UPLOAD_ROOT.is_dir():
        print(f"✗ {UPLOAD_ROOT} not found — run this from the backend/ directory")
        return 1

    db = SessionLocal()
    created = {"tenants": 0, "hunts": 0, "datasets": 0}
    try:
        for tdir in sorted(UPLOAD_ROOT.glob("tenant_*")):
            m = re.match(r"tenant_(\d+)$", tdir.name)
            if not m:
                continue
            tid = int(m.group(1))
            name = NAME_OVERRIDES.get(tid, f"Client {tid}")
            logo = next((p for p in tdir.iterdir() if p.name.lower().startswith("logo")), None)

            tenant = db.get(Tenant, tid)
            if tenant is None:
                tenant = Tenant(
                    id=tid, name=name, slug=_slugify(name, tid),
                    logo_path=str(logo) if logo else None,
                )
                db.add(tenant)
                db.flush()
                created["tenants"] += 1
                print(f"✓ tenant {tid}: {name}" + (f"  (logo: {logo.name})" if logo else ""))
            else:
                print(f"· tenant {tid}: {tenant.name} (exists, skipped)")

            for hdir in sorted(tdir.glob("hunt_*")):
                hm = re.match(r"hunt_(\d+)$", hdir.name)
                if not hm:
                    continue
                hid = int(hm.group(1))
                hunt = db.get(Hunt, hid)
                if hunt is None:
                    hunt = Hunt(
                        id=hid, tenant_id=tid,
                        name=HUNT_NAMES.get(hid, f"Recovered hunt {hid}"),
                        status="created",
                    )
                    db.add(hunt)
                    db.flush()
                    created["hunts"] += 1
                    print(f"  ✓ hunt {hid}: {hunt.name}")
                else:
                    print(f"  · hunt {hid}: {hunt.name} (exists, skipped)")

                for csv in sorted(hdir.glob("*.csv")):
                    fpath = str(csv)
                    exists = db.query(Dataset).filter_by(file_path=fpath).first()
                    if exists:
                        print(f"    · {csv.name} (exists, skipped)")
                        continue
                    rows, cols, columns = _dataset_meta(csv)
                    db.add(Dataset(
                        tenant_id=tid, hunt_id=hid,
                        filename=_clean_filename(csv.name),
                        file_path=fpath,
                        file_size=os.path.getsize(csv),
                        row_count=rows, col_count=cols, columns=columns,
                        status="uploaded",
                    ))
                    created["datasets"] += 1
                    print(f"    ✓ {_clean_filename(csv.name)}  ({rows} rows × {cols} cols)")

        _reset_sequences(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\nDone. Created {created['tenants']} tenants, "
          f"{created['hunts']} hunts, {created['datasets']} datasets.")
    print("Next: open each hunt, re-attach its methodology doc, and run analysis "
          "(findings regenerate on the new engine).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
