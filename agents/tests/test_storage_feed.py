"""AgentFeed davranışı her iki arka uçta aynıdır; DynamoDB'de süreçler arası sıra numarası çakışmaz."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from agents import feed as feed_module


def test_add_numbers_events_and_items_filter(storage):
    f = storage.feed()
    a = f.add(agent="review", kind="proposal", summary="öneri", day=3, status="awaiting_approval", record="M1", old=1.5)
    b = f.add(agent="region", kind="question", summary="soru", day=3, address=7)
    assert (a["n"], b["n"]) == (1, 2) and a["record"] == "M1" and a["old"] == 1.5 and b["status"] == "applied"
    assert isinstance(a["time"], (int, float)) and a["day"] == 3 and a["type"] == "proposal"
    assert [o["n"] for o in f.items()] == [1, 2] and [o["n"] for o in f.items(after=1)] == [2]
    assert [o["n"] for o in f.items(agent="review")] == [1] and [o["n"] for o in f.items(status="applied")] == [2]
    assert f.events == f.items()


def test_update_merges_fields(storage):
    f = storage.feed()
    f.add(agent="review", kind="proposal", summary="öneri", status="awaiting_approval", detail={"a": [1, 2]})
    o = f.update(1, status="approved", note="ok")
    assert o["status"] == "approved" and o["note"] == "ok" and o["summary"] == "öneri" and o["detail"] == {"a": [1, 2]}
    assert f.items()[0] == o and f.update(99, status="x") is None


def test_reset_restarts_numbering(storage):
    f = storage.feed()
    f.add(agent="review", kind="report", summary="r")
    f.reset()
    assert f.items() == [] and f.add(agent="review", kind="report", summary="r2")["n"] == 1


def test_window_keeps_last_max_events(storage, monkeypatch):
    monkeypatch.setattr(feed_module, "MAX_EVENTS", 3)
    f = storage.feed()
    for i in range(5):
        f.add(agent="review", kind="report", summary=str(i))
    assert [o["n"] for o in f.items()] == [3, 4, 5] and f.add(agent="x", kind="y", summary="z")["n"] == 6


def test_new_instance_sees_events(storage):
    storage.feed().add(agent="review", kind="report", summary="r", day=1)
    assert [o["summary"] for o in storage.feed().items()] == ["r"]


def test_dynamo_concurrent_adds_are_gapless(dynamo):
    feeds = [dynamo.feed() for _ in range(4)]
    with ThreadPoolExecutor(4) as ex:
        out = list(ex.map(lambda i: feeds[i % 4].add(agent="review", kind="report", summary=str(i)), range(16)))
    assert sorted(o["n"] for o in out) == list(range(1, 17))
    assert [o["n"] for o in feeds[0].items()] == list(range(1, 17))
    assert sorted(o["summary"] for o in feeds[1].items()) == sorted(str(i) for i in range(16))


def test_dynamo_update_from_other_instance(dynamo):
    a, b = dynamo.feed(), dynamo.feed()
    a.add(agent="review", kind="proposal", summary="öneri", status="awaiting_approval")
    b.update(1, status="rejected")
    assert a.items(status="rejected")[0]["n"] == 1


def test_dynamo_rejects_key_fields_in_update(dynamo):
    f = dynamo.feed()
    f.add(agent="review", kind="report", summary="r")
    with pytest.raises(ValueError):
        f.update(1, PK="x")
