"""Phase B — deterministic correlation graph (links, clusters, cross-dataset, timeline)."""
from app.services import correlation_engine as ce

_FINDINGS = [
    {"id": 1, "finding_ref": "F-001", "title": "ROPC spray", "category": "suspicious",
     "dataset_id": 8, "time_range": {"start": "2026-05-20T00:14:00Z"},
     "entities": {"users": ["camilo.burgos"], "ips": ["100.27.38.176"]}},
    {"id": 2, "finding_ref": "F-002", "title": "Lateral movement", "category": "suspicious",
     "dataset_id": 3, "time_range": {"start": "2026-05-20T00:25:00Z"},
     "entities": {"users": ["camilo.burgos"], "hosts": ["EP-01"]}},
    {"id": 3, "finding_ref": "F-003", "title": "Mailbox volume", "category": "risky",
     "dataset_id": 10, "time_range": {"start": "2026-05-20T01:00:00Z"},
     "entities": {"users": ["svc_integration"]}},
]
_INDEX = {
    8: {"entities": {"users": ["camilo.burgos"], "ips": ["100.27.38.176"]}},
    3: {"entities": {"users": ["camilo.burgos"], "hosts": ["EP-01"]}},
    10: {"entities": {"users": ["svc_integration", "camilo.burgos"]}},
}


def test_links_on_shared_entity():
    links = ce.build_links(_FINDINGS)
    assert len(links) == 1
    assert {links[0]["a_ref"], links[0]["b_ref"]} == {"F-001", "F-002"}
    assert links[0]["shared"][0]["value"] == "camilo.burgos"


def test_clusters_are_connected_components_of_two_plus():
    pkg = ce.build_correlation_package(_FINDINGS, _INDEX)
    assert pkg["clusters"] == [[1, 2]]          # F-003 stands alone, excluded


def test_cross_dataset_presence_flags_other_datasets():
    cd = ce.cross_dataset_presence(_FINDINGS, _INDEX)
    # camilo (finding 1, dataset 8) also appears in datasets 3 and 10
    hit = next(h for h in cd[1] if h["entity"] == "camilo.burgos")
    assert hit["also_in_datasets"] == [3, 10]


def test_timeline_is_chronological():
    tl = ce.timeline(_FINDINGS)
    assert [t["finding_ref"] for t in tl] == ["F-001", "F-002", "F-003"]


def test_no_entities_no_links():
    bare = [{"id": 1, "finding_ref": "F-001", "entities": {}},
            {"id": 2, "finding_ref": "F-002", "entities": {}}]
    pkg = ce.build_correlation_package(bare, {})
    assert pkg["links"] == [] and pkg["clusters"] == []
