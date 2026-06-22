"""
Global module configuration store.

LENS is organized into modules. This file manages the editable guides/standards
for the **Structured Threat Hunt** module — the Investigation Protocol, the
Finding Format, and the Finding Categorization. They ship as version-controlled
seed defaults (app/seeds/*.md) but are stored in the DB so the operator can edit
them in the Configuration page without code changes.

These are deliberately NOT tenant-scoped: they are the threat-hunt service's own
standards, shared across every client. (Client-specific context — baselines,
approved software — remains per-tenant in the knowledge base.)
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ModuleConfig

# Module identifier — future LENS modules register their own.
STRUCTURED_THREAT_HUNT = "structured_threat_hunt"

_SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"

# key -> (display title, seed filename). Order is the display order.
CONFIG_KEYS: dict[str, tuple[str, str]] = {
    "analysis_instructions": ("Investigation Protocol", "analysis_instructions.md"),
    "finding_format": ("Finding Format", "finding_format.md"),
    "finding_categories": ("Finding Categorization", "finding_categories.md"),
}


def _seed_text(filename: str) -> str:
    path = _SEEDS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def seed_defaults(db: Session) -> None:
    """Create any missing Structured Threat Hunt config rows from seed files."""
    existing = {
        row.key
        for row in db.query(ModuleConfig.key).filter_by(module=STRUCTURED_THREAT_HUNT)
    }
    created = False
    for key, (title, filename) in CONFIG_KEYS.items():
        if key in existing:
            continue
        db.add(
            ModuleConfig(
                module=STRUCTURED_THREAT_HUNT,
                key=key,
                title=title,
                content=_seed_text(filename),
            )
        )
        created = True
    if created:
        db.commit()


def get_value(db: Session, key: str, module: str = STRUCTURED_THREAT_HUNT) -> str:
    """Return stored content for a key, falling back to the seed default."""
    row = db.query(ModuleConfig).filter_by(module=module, key=key).first()
    if row and row.content:
        return row.content
    title, filename = CONFIG_KEYS.get(key, ("", ""))
    return _seed_text(filename) if filename else ""


def list_configs(db: Session, module: str = STRUCTURED_THREAT_HUNT) -> list[ModuleConfig]:
    seed_defaults(db)
    return (
        db.query(ModuleConfig)
        .filter_by(module=module)
        .order_by(ModuleConfig.key)
        .all()
    )


def upsert(
    db: Session, key: str, content: str, *, module: str = STRUCTURED_THREAT_HUNT
) -> ModuleConfig:
    row = db.query(ModuleConfig).filter_by(module=module, key=key).first()
    if row is None:
        title = CONFIG_KEYS.get(key, (key.replace("_", " ").title(), ""))[0]
        row = ModuleConfig(module=module, key=key, title=title, content=content)
        db.add(row)
    else:
        row.content = content
    db.commit()
    db.refresh(row)
    return row
