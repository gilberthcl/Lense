"""Dataset locator ranking — pure (descriptive name first, then entity overlap)."""
from app.services import dataset_locator as dl


def _datasets():
    return [
        {"id": 1, "filename": "1-process-creation.csv", "entities": ["host-9"]},
        {"id": 2, "filename": "5-ropc-signins.csv", "entities": ["svc-acct", "1.2.3.4"]},
        {"id": 3, "filename": "8-dns-queries.csv", "entities": ["host-2"]},
    ]


def test_descriptive_filename_drives_ranking():
    ranked = dl.rank_datasets(
        "Suspicious ROPC sign-ins by external service accounts", _datasets()
    )
    # The ropc-signins dataset should rank first purely on the name match.
    assert ranked[0]["id"] == 2
    assert ranked[0]["score"] >= ranked[1]["score"]


def test_entity_overlap_breaks_ties_when_names_dont_match():
    # A finding whose text mentions an entity present in dataset 1 but no name hit.
    datasets = [
        {"id": 1, "filename": "a.csv", "entities": ["host-9", "evil.exe"]},
        {"id": 2, "filename": "b.csv", "entities": ["host-2"]},
    ]
    ranked = dl.rank_datasets("Malware evil.exe seen on host-9", datasets)
    assert ranked[0]["id"] == 1
    assert ranked[0]["entity_hits"] >= 1


def test_empty_inputs_are_safe():
    assert dl.rank_datasets("", []) == []
    ranked = dl.rank_datasets("anything", [{"id": 1, "filename": "", "entities": []}])
    assert ranked[0]["id"] == 1 and ranked[0]["score"] == 0.0
