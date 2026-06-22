"""
Local single-operator access PIN.

A 6-character PIN is hashed (SHA-256 + static salt) and stored in the global
ModuleConfig table. The returned token IS that hash — the client sends it as a
bearer credential on every request and the API middleware compares it (constant
time) against the cached hash.

This protects the local, on-box deployment for a single operator; it is not a
multi-user auth system. The hash is cached in memory so request-time checks
need no DB round-trip.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.models import ModuleConfig

MODULE = "global"
KEY = "auth"
SALT = "lens-thfe::pin::v1"

_pin_hash: str | None = None  # cached; None = not configured


def hash_pin(pin: str) -> str:
    return hashlib.sha256(f"{SALT}:{pin}".encode()).hexdigest()


def _row(db: Session) -> ModuleConfig | None:
    return db.query(ModuleConfig).filter_by(module=MODULE, key=KEY).first()


def refresh(db: Session) -> None:
    """Reload the cached PIN hash from the DB (call on startup and after changes)."""
    global _pin_hash
    row = _row(db)
    if row and row.content:
        try:
            _pin_hash = json.loads(row.content).get("pin_hash") or None
        except json.JSONDecodeError:
            _pin_hash = None
    else:
        _pin_hash = None


def configured() -> bool:
    return _pin_hash is not None


def check(token: str) -> bool:
    if _pin_hash is None:
        return True  # not configured yet — allow bootstrap
    return bool(token) and hmac.compare_digest(token, _pin_hash)


def _store(db: Session, pin_hash: str) -> None:
    row = _row(db)
    content = json.dumps({"pin_hash": pin_hash})
    if row is None:
        db.add(ModuleConfig(module=MODULE, key=KEY, title="Access PIN", content=content))
    else:
        row.content = content
    db.commit()
    refresh(db)


def setup(db: Session, pin: str) -> str:
    """Set the PIN for the first time. Returns the access token (the hash)."""
    h = hash_pin(pin)
    _store(db, h)
    return h


def verify(db: Session, pin: str) -> str | None:
    """Return the token if the PIN matches the stored hash, else None."""
    if _pin_hash is None:
        return None
    h = hash_pin(pin)
    return h if hmac.compare_digest(h, _pin_hash) else None


def change(db: Session, current_pin: str, new_pin: str) -> str | None:
    if verify(db, current_pin) is None:
        return None
    return setup(db, new_pin)
