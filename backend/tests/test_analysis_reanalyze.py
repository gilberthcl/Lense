"""Re-analysis ref numbering — must not reuse a ref still held by another
dataset's finding when only a subset is re-analyzed."""
from app.services import analysis_runner


class _RefQuery:
    def __init__(self, refs):
        self._refs = refs

    def filter_by(self, **_kw):
        return self

    def __iter__(self):
        return iter((r,) for r in self._refs)


class _FakeDB:
    def __init__(self, refs):
        self._refs = refs

    def query(self, _col):
        return _RefQuery(self._refs)


def test_next_seq_continues_from_max_not_count():
    # 5 findings but with a gap (F-003 deleted): count()=4 would collide with
    # F-004; max+1 = 6 is safe.
    db = _FakeDB(["F-001", "F-002", "F-004", "F-005", "F-007"])
    assert analysis_runner._next_finding_seq(db, hunt_id=1) == 8


def test_next_seq_empty_starts_at_one():
    assert analysis_runner._next_finding_seq(_FakeDB([]), hunt_id=1) == 1
