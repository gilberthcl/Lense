"""Golden-eval metrics + runner core (no model / no DB)."""
from app.services import eval_metrics, eval_runner

_EVIDENCE = {
    "entities": {"hosts": ["WKSTN-01"], "users": ["jdoe"]},
    "sample_rows": [{"host": "WKSTN-01", "user": "jdoe", "process": "mimikatz.exe"}],
}


def _expected(cat="malicious", ents=("WKSTN-01", "jdoe")):
    return {"category": cat, "entities": list(ents)}


def _produced(cat="malicious", assets=("WKSTN-01",), users=("jdoe",)):
    return {"category": cat, "affected_assets": list(assets), "affected_users": list(users)}


def test_matches_on_category_and_entity_overlap():
    assert eval_metrics.matches(_expected(), _produced()) is True
    assert eval_metrics.matches(_expected(), _produced(cat="suspicious")) is False  # category differs
    assert eval_metrics.matches(_expected(), _produced(assets=("OTHER",), users=("x",))) is False


def test_score_case_true_positive_no_hallucination():
    s = eval_metrics.score_case([_expected()], [_produced()], _EVIDENCE)
    assert s == {"tp": 1, "fp": 0, "fn": 0, "n_expected": 1, "n_produced": 1, "hallucinated": 0}


def test_score_case_flags_hallucinated_entity():
    ghost = _produced(assets=("GHOST-PC",), users=("nobody",))
    s = eval_metrics.score_case([], [ghost], _EVIDENCE)
    assert s["hallucinated"] == 1 and s["fp"] == 1


def test_benign_case_perfect_when_nothing_produced():
    s = eval_metrics.score_case([], [], _EVIDENCE)
    agg = eval_metrics.aggregate([s])
    assert agg["precision"] == 1.0 and agg["recall"] == 1.0
    assert agg["hallucination_rate"] == 0.0


def test_aggregate_precision_recall_and_parse_rate():
    scores = [
        eval_metrics.score_case([_expected()], [_produced()], _EVIDENCE),          # tp
        eval_metrics.score_case([_expected(ents=("WS-9",))], [], _EVIDENCE),        # fn (missed)
    ]
    agg = eval_metrics.aggregate(scores, parse_errors=1)
    assert agg["tp"] == 1 and agg["fn"] == 1
    assert agg["recall"] == 0.5
    assert agg["precision"] == 1.0
    assert agg["parse_error_rate"] == 0.5  # 1 of 2 cases


def test_compare_flags_regression():
    base = {"precision": 0.9, "recall": 0.8, "f1": 0.85, "hallucination_rate": 0.05, "parse_error_rate": 0.0}
    worse = {**base, "recall": 0.7}            # -0.1 recall
    better = {**base, "precision": 0.95}
    assert eval_metrics.compare(base, worse)["regressed"] is True
    assert eval_metrics.compare(base, better)["regressed"] is False
    more_hallucination = {**base, "hallucination_rate": 0.2}
    assert eval_metrics.compare(base, more_hallucination)["regressed"] is True


def test_run_eval_uses_injected_analyze_fn():
    cases = [
        {"name": "c1", "source": "synthetic", "evidence_package": _EVIDENCE, "expected": [_expected()]},
        {"name": "c2", "source": "synthetic", "evidence_package": _EVIDENCE, "expected": []},
        {"name": "boom", "source": "synthetic", "evidence_package": _EVIDENCE, "expected": [_expected()]},
    ]

    def fake_analyze(case):
        if case["name"] == "c1":
            return [_produced()], False        # correct hit
        if case["name"] == "boom":
            raise RuntimeError("model exploded")  # must be counted, not raised
        return [], False                        # benign: nothing produced

    report = eval_runner.run_eval(cases, fake_analyze)
    assert report["metrics"]["cases"] == 3
    assert report["metrics"]["tp"] == 1
    assert report["metrics"]["parse_error_rate"] == round(1 / 3, 4)  # the boom case
    assert {r["name"] for r in report["cases"]} == {"c1", "c2", "boom"}


def test_synthetic_golden_cases_load_and_are_well_formed():
    cases = eval_runner.load_synthetic_cases()
    names = {c["name"] for c in cases}
    assert {"synthetic-malicious-mimikatz", "synthetic-benign-approved-software"} <= names
    for c in cases:
        assert "evidence_package" in c and "expected" in c
