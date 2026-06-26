"""Phase B — deterministic correlation graph (links, clusters, cross-dataset, timeline)."""
from app.services import correlation_engine as ce

_FINDINGS = [
    {"id": 1, "finding_ref": "F-001", "title": "ROPC spray", "category": "suspicious",
     "dataset_id": 8, "time_range": {"start": "2026-05-20T00:14:00Z"},
     "entities": {"users": ["jdoe"], "ips": ["1.1.1.1"]}},
    {"id": 2, "finding_ref": "F-002", "title": "Lateral movement", "category": "suspicious",
     "dataset_id": 3, "time_range": {"start": "2026-05-20T00:25:00Z"},
     "entities": {"users": ["jdoe"], "hosts": ["WKSTN-01"]}},
    {"id": 3, "finding_ref": "F-003", "title": "Mailbox volume", "category": "risky",
     "dataset_id": 10, "time_range": {"start": "2026-05-20T01:00:00Z"},
     "entities": {"users": ["svc_app"]}},
]
_INDEX = {
    8: {"entities": {"users": ["jdoe"], "ips": ["1.1.1.1"]}},
    3: {"entities": {"users": ["jdoe"], "hosts": ["WKSTN-01"]}},
    10: {"entities": {"users": ["svc_app", "jdoe"]}},
}


def test_links_on_shared_entity():
    links = ce.build_links(_FINDINGS)
    assert len(links) == 1
    assert {links[0]["a_ref"], links[0]["b_ref"]} == {"F-001", "F-002"}
    assert links[0]["shared"][0]["value"] == "jdoe"


def test_clusters_are_connected_components_of_two_plus():
    pkg = ce.build_correlation_package(_FINDINGS, _INDEX)
    assert pkg["clusters"] == [[1, 2]]          # F-003 stands alone, excluded


def test_cross_dataset_presence_flags_other_datasets():
    cd = ce.cross_dataset_presence(_FINDINGS, _INDEX)
    # jdoe (finding 1, dataset 8) also appears in datasets 3 and 10
    hit = next(h for h in cd[1] if h["entity"] == "jdoe")
    assert hit["also_in_datasets"] == [3, 10]


def test_timeline_is_chronological():
    tl = ce.timeline(_FINDINGS)
    assert [t["finding_ref"] for t in tl] == ["F-001", "F-002", "F-003"]


def test_no_entities_no_links():
    bare = [{"id": 1, "finding_ref": "F-001", "entities": {}},
            {"id": 2, "finding_ref": "F-002", "entities": {}}]
    pkg = ce.build_correlation_package(bare, {})
    assert pkg["links"] == [] and pkg["clusters"] == []


def test_run_llm_correlation_parses_output(monkeypatch):
    payload = (
        '{"merges": [{"primary_ref":"F-001","duplicate_refs":["F-002"],"reason":"dup"}],'
        ' "enrichments": [], '
        '"incidents": [{"title":"chain","finding_refs":["F-001","F-002"]}]}'
    )
    monkeypatch.setattr(ce.ollama, "analyst", lambda sys, user: payload)
    out = ce.run_llm_correlation(_FINDINGS, ce.build_correlation_package(_FINDINGS, _INDEX))
    assert out["merges"][0]["primary_ref"] == "F-001"
    assert out["incidents"][0]["finding_refs"] == ["F-001", "F-002"]


def test_run_llm_correlation_survives_bad_json(monkeypatch):
    monkeypatch.setattr(ce.ollama, "analyst", lambda sys, user: "not json at all")
    out = ce.run_llm_correlation(_FINDINGS, ce.build_correlation_package(_FINDINGS, _INDEX))
    assert out["merges"] == [] and out["incidents"] == [] and out["parse_error"] is True
