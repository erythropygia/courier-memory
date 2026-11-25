"""MemoryBook davranışı her iki arka uçta aynıdır (CM_STORAGE=file | dynamodb)."""
import pytest

from agents.memorybook import TTL_DAYS, MemoryWriteError
from agents.tests.storage_support import SEED_DAY


def test_ensure_seeds_once_and_keeps_agent_writes(storage):
    book = storage.book()
    assert book.seed_day is None and book.entries == []
    book.ensure(SEED_DAY)
    assert book.seed_day == SEED_DAY and len(book.entries) == 5
    assert all(e["status"] == "active" and e["source"] == "simulation" for e in book.entries)
    book.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    book.ensure(SEED_DAY + 1)
    assert book.seed_day == SEED_DAY and len(book.entries) == 6


def test_reset_replaces_entries_and_clears_log(storage):
    book = storage.book()
    assert book.reset(SEED_DAY) == 5
    book.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id="N1")
    assert len(book.log) == 1
    assert book.reset(SEED_DAY + 1) == 5
    assert book.seed_day == SEED_DAY + 1 and len(book.entries) == 5 and book.log == []


def test_upsert_creates_then_strengthens(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    e, created = book.upsert(address=1, kind="lunch_break", text="", day=SEED_DAY, note_id="N1", window=[720, 810])
    assert created and e["id"] == "M00905" and e["sources"] == 1 and e["window"] == [720, 810]
    assert e["text"] and e["note_ids"] == ["N1"] and e["source"] == "agent" and e["ttl_until"] is None
    e2, created2 = book.upsert(address=1, kind="lunch_break", text="Öğle arası 12-13.", day=SEED_DAY + 1,
                               note_id="N2", source="harvest")
    assert not created2 and e2["id"] == e["id"] and e2["sources"] == 2 and e2["last_day"] == SEED_DAY + 1
    assert e2["note_ids"] == ["N1", "N2"] and e2["source_list"] == ["agent", "harvest"] and e2["text"] == "Öğle arası 12-13."
    assert book.get(e["id"]) == e2
    assert [x["operation"] for x in book.log] == ["added", "updated"]


def test_upsert_temporary_kind_gets_ttl(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    e, created = book.upsert(address=8, kind="roadwork", text="", day=SEED_DAY, note_id=None)
    assert not created and e["ttl_until"] == SEED_DAY + TTL_DAYS and e["sources"] == 4


@pytest.mark.parametrize("kwargs, match", [
    ({"kind": "nope", "text": "x"}, "Bilinmeyen"),
    ({"kind": "park", "text": ""}, "ipucu metni gerekli"),
    ({"kind": "bell", "text": "x" * 141}, "140"),
    ({"kind": "bell", "text": "", "address": 999}, "Geçersiz adres"),
    ({"kind": "bell", "text": "", "window": [720, 810]}, "pencere"),
])
def test_upsert_validation_writes_nothing(storage, kwargs, match):
    book = storage.book()
    book.reset(SEED_DAY)
    args = {"address": 1, "day": SEED_DAY, "note_id": None, **kwargs}
    with pytest.raises(MemoryWriteError, match=match):
        book.upsert(**args)
    assert len(book.entries) == 5 and book.log == []


def test_for_address_filters_status_and_ttl(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    assert {e["kind"] for e in book.for_address(5, SEED_DAY)} == {"bell", "park"}
    assert [e["kind"] for e in book.for_address(8, 35)] == ["roadwork"] and book.for_address(8, 36) == []
    bell = next(e for e in book.for_address(5, SEED_DAY) if e["kind"] == "bell")
    assert book.drop(bell["id"], SEED_DAY, "yanlış")
    assert [e["kind"] for e in book.for_address(5, SEED_DAY)] == ["park"]


def test_feedback_counts_and_drops(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    first = book.entries[0]
    e = book.feedback(first["id"], True, SEED_DAY + 2)
    assert e["sources"] == first["sources"] + 1 and e["confirmed_day"] == SEED_DAY + 2 and e["last_day"] == SEED_DAY + 2
    e = book.feedback(first["id"], False, SEED_DAY + 3)
    assert e["status"] == "dropped" and e["dropped_day"] == SEED_DAY + 3
    assert book.feedback("M99999", True, SEED_DAY) is None
    assert [x["operation"] for x in book.log] == ["confirmation", "dropped"]


def test_flag_undo_and_drop(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    eid = book.entries[1]["id"]
    assert book.flag_for_confirmation(eid, SEED_DAY, "deneme") and not book.flag_for_confirmation(eid, SEED_DAY, "deneme")
    assert book.get(eid)["needs_confirmation"] and book.get(eid)["confirmation_reason"] == "deneme"
    assert book.drop(eid, SEED_DAY, "eski") and book.get(eid)["drop_reason"] == "eski"
    assert not book.flag_for_confirmation(eid, SEED_DAY, "x")
    assert book.undo(eid, SEED_DAY)
    e = book.get(eid)
    assert e["status"] == "active" and not {"dropped_day", "drop_reason", "needs_confirmation", "confirmation_reason"} & set(e)
    assert not book.undo("M99999", SEED_DAY) and not book.drop("M99999", SEED_DAY, "x")


def test_summary_counts_alive_and_lists_recent_non_simulation(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    book.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    s = book.summary(SEED_DAY)
    assert s["total"] == 6 and s["type_distribution"]["bell"] == 2
    assert [e["address"] for e in s["last"]] == [1]
    assert book.summary(40)["total"] == 5            # roadwork ttl 35 geçti


def test_new_instance_reads_persisted_state(storage):
    book = storage.book()
    book.reset(SEED_DAY)
    e, _ = book.upsert(address=2, kind="reception", text="", day=SEED_DAY, note_id="N9")
    book.feedback(e["id"], True, SEED_DAY)
    other = storage.book()
    assert other.seed_day == SEED_DAY and other.get(e["id"])["sources"] == 2
    assert [x["operation"] for x in other.log] == ["added", "confirmation"]
    assert [x["id"] for x in other.entries] == [x["id"] for x in book.entries]


def test_other_run_starts_empty(storage):
    from agents.tests.storage_support import FakeRun

    storage.book().reset(SEED_DAY)
    assert storage.book(FakeRun(run_id="another-run")).seed_day is None
