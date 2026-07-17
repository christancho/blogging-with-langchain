import json
from api.log_stream import channel_for, build_payloads, count_completed_lines, done_payload


def test_channel_for():
    assert channel_for("abc-123") == "blog_run_abc-123"


def test_build_payloads_single_line():
    out = build_payloads(5, "hello")
    assert len(out) == 1
    assert json.loads(out[0]) == {"seq": 5, "line": "hello"}


def test_build_payloads_splits_oversized_line():
    big = "x" * 15000
    out = build_payloads(7, big, max_bytes=7000)
    assert len(out) == 3
    frags = [json.loads(p) for p in out]
    assert [f["frag"] for f in frags] == [0, 1, 2]
    assert all(f["seq"] == 7 for f in frags)
    assert "".join(f["line"] for f in frags) == big


def test_count_completed_lines():
    assert count_completed_lines(None) == 0
    assert count_completed_lines("") == 0
    assert count_completed_lines("a\nb\n") == 2
    assert count_completed_lines("a\nb\npartial") == 2  # trailing partial not counted


def test_done_payload():
    assert json.loads(done_payload("completed")) == {"done": True, "status": "completed"}
