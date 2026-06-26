"""Training Hunt (W3) — schema contract for hunt kind."""
from app.schemas import HuntCreate


def test_hunt_kind_defaults_to_live():
    assert HuntCreate(name="h").kind == "live"


def test_hunt_kind_training_accepted():
    assert HuntCreate(name="h", kind="training").kind == "training"
