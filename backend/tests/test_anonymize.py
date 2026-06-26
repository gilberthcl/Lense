"""Training-example anonymisation (W5, pure)."""
from types import SimpleNamespace

from app.services import anonymize as anon


def _finding(**kw):
    base = dict(
        entities={"hosts": ["EP-01"], "users": ["camilo"], "ips": ["10.0.0.5"]},
        affected_assets=["EP-01"], affected_users=["camilo"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_map_assigns_typed_placeholders():
    m = anon.build_map(_finding())
    assert m["ep-01"] == "HOST_1"
    assert m["camilo"] == "USER_1"
    assert m["10.0.0.5"] == "IP_1"


def test_build_map_skips_short_tokens():
    m = anon.build_map(_finding(entities={"users": ["ab"]}, affected_assets=[], affected_users=[]))
    assert m == {}  # "ab" < 3 chars → not mapped (would corrupt text)


def test_scrub_text_case_insensitive_and_longest_first():
    m = {"ep-01": "HOST_1", "camilo": "USER_1"}
    out = anon.scrub_text("Host EP-01 and user Camilo and ep-01 again", m)
    assert out == "Host HOST_1 and user USER_1 and HOST_1 again"


def test_anonymize_example_scrubs_messages_not_meta():
    ex = {
        "messages": [
            {"role": "user", "content": "evidence on EP-01 by camilo"},
            {"role": "assistant", "content": '{"findings":[{"affected_assets":["EP-01"]}]}'},
        ],
        "meta": {"finding_ref": "F-001"},
    }
    out = anon.anonymize_example(ex, _finding())
    assert "EP-01" not in out["messages"][0]["content"]
    assert "HOST_1" in out["messages"][0]["content"]
    assert "HOST_1" in out["messages"][1]["content"]
    assert out["meta"]["finding_ref"] == "F-001"   # meta preserved
    assert out["meta"]["anonymized"] is True


def test_anonymize_noop_without_entities():
    bare = SimpleNamespace(entities=None, affected_assets=None, affected_users=None)
    ex = {"messages": [{"role": "user", "content": "nothing to scrub"}], "meta": {}}
    assert anon.anonymize_example(ex, bare) == ex
