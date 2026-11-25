"""DynamoDB'ye özgü MemoryBook davranışı: süreçler arası görünürlük, eşzamanlı yazım, idempotent tohumlama."""
from concurrent.futures import ThreadPoolExecutor

import boto3
from boto3.dynamodb.conditions import Key

from agents.storage import dynamo_keys as keys
from agents.tests.storage_support import SEED_DAY, TEST_REGION, TEST_TABLE


def _table():
    return boto3.resource("dynamodb", region_name=TEST_REGION).Table(TEST_TABLE)


def _meta(run_id="fake-run"):
    return _table().get_item(Key=keys.memory_meta_key(run_id), ConsistentRead=True).get("Item")


def _partition(pk):
    return _table().query(KeyConditionExpression=Key("PK").eq(pk), ConsistentRead=True)["Items"]


def test_writes_are_visible_to_live_instances(dynamo):
    a, b = dynamo.book(), dynamo.book()
    a.ensure(SEED_DAY)
    assert b.seed_day == SEED_DAY and len(b.entries) == 5          # b, a'nın tohumunu görür
    e, _ = b.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    assert a.get(e["id"]) == e and len(a.log) == 1                  # a önbelleğine güvenmez: sürümü kontrol eder
    a.drop(e["id"], SEED_DAY, "x")
    assert b.for_address(1, SEED_DAY) == []
    b.reset(SEED_DAY + 1)
    assert a.seed_day == SEED_DAY + 1 and a.log == [] and a.get(e["id"]) is None


def test_items_are_written_per_entry_not_as_one_document(dynamo):
    book = dynamo.book()
    book.reset(SEED_DAY)
    e, _ = book.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    meta = _meta()
    items = _partition(keys.memory_partition(book.run.run_id, meta["generation"]))
    sks = sorted(i["SK"] for i in items)
    assert sks == sorted([f"ENTRY#{x['id']}" for x in book.entries] + ["LOG#0000000001"])
    assert meta["version"] == 1 and meta["seed_day"] == SEED_DAY


def test_concurrent_upserts_on_same_slot_merge_into_one_entry(dynamo):
    dynamo.book().reset(SEED_DAY)
    books = [dynamo.book() for _ in range(4)]

    def write(i):
        return books[i % 4].upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=f"N{i}")

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(write, range(12)))
    assert sum(created for _, created in results) == 1
    fresh = dynamo.book()
    bells = [e for e in fresh.entries if e["address"] == 1 and e["kind"] == "bell"]
    assert len(bells) == 1 and bells[0]["sources"] == 12 and sorted(bells[0]["note_ids"]) == sorted(f"N{i}" for i in range(12))
    assert len(fresh.log) == 12 and [x["operation"] for x in fresh.log].count("added") == 1


def test_concurrent_creates_get_unique_ids(dynamo):
    dynamo.book().reset(SEED_DAY)
    books = [dynamo.book() for _ in range(3)]
    kinds = ["bell", "reception", "safety", "back_entry", "lunch_break", "saturday_closed"]

    def write(i):
        return books[i % 3].upsert(address=10 + i, kind=kinds[i], text="", day=SEED_DAY, note_id=None)[0]["id"]

    with ThreadPoolExecutor(3) as ex:
        ids = list(ex.map(write, range(6)))
    assert len(set(ids)) == 6 and len(dynamo.book().entries) == 11


def test_concurrent_feedback_counts_every_confirmation(dynamo):
    dynamo.book().reset(SEED_DAY)
    books = [dynamo.book() for _ in range(4)]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda i: books[i % 4].feedback("M00900", True, SEED_DAY), range(8)))
    assert dynamo.book().get("M00900")["sources"] == 1 + 8


def test_seeding_is_idempotent(dynamo):
    a = dynamo.book()
    a.ensure(SEED_DAY)
    gen = _meta()["generation"]
    b = dynamo.book()
    b.ensure(SEED_DAY)
    assert _meta()["generation"] == gen                              # ikinci süreç yeniden tohumlamaz
    assert b.reset(SEED_DAY) == 5 and _meta()["generation"] == gen   # dokunulmamış aynı gün: atlanır
    b.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    b.reset(SEED_DAY)
    assert _meta()["generation"] != gen and len(a.entries) == 5      # değişmiş: yeniden tohumlanır


def test_concurrent_ensure_seeds_a_single_generation(dynamo):
    books = [dynamo.book() for _ in range(4)]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda b: b.ensure(SEED_DAY), books))
    meta = _meta()
    assert all(len(b.entries) == 5 for b in books)
    entry_pks = {i["PK"] for i in _table().scan()["Items"] if i["SK"].startswith("ENTRY#")}
    assert entry_pks == {keys.memory_partition("fake-run", meta["generation"])}   # kaybeden tohumlar silinir


def test_old_generations_are_purged_with_one_generation_grace(dynamo):
    book = dynamo.book()
    gens = []
    for d in range(3):
        book.reset(SEED_DAY + d)
        gens.append(_meta()["generation"])
    assert _partition(keys.memory_partition("fake-run", gens[0])) == []
    assert len(_partition(keys.memory_partition("fake-run", gens[1]))) == 5   # okuyanlar için bir nesil bekletilir
    assert len(_partition(keys.memory_partition("fake-run", gens[2]))) == 5


def test_seeding_real_day_matches_file_backend(dynamo, tmp_path, monkeypatch):
    from agents.memorybook import MemoryBook
    from agents.rundata import RunData

    run = RunData()
    day = run.meta["critical"]["day"]
    remote = MemoryBook(run)
    remote.ensure(day)
    monkeypatch.setenv("CM_STORAGE", "file")
    local = MemoryBook(run, tmp_path / "real.json")
    local.ensure(day)
    assert remote.entries == local.entries and remote.summary(day) == local.summary(day)
    assert all(remote.for_address(a, day) == local.for_address(a, day) for a in range(0, 40000, 97))


def test_sync_interval_bounds_staleness_but_writes_stay_consistent(dynamo, monkeypatch):
    monkeypatch.setenv("CM_DYNAMODB_SYNC_SECONDS", "3600")
    a, b = dynamo.book(), dynamo.book()
    a.reset(SEED_DAY)
    assert len(b.entries) == 5
    e, _ = a.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    assert a.get(e["id"]) == e                     # kendi yazımı hemen görünür
    assert b.get(e["id"]) is None                  # aralık dolmadan diğer süreç önbellekten okur (sınırlı bayatlık)
    e2, created = b.upsert(address=1, kind="bell", text="", day=SEED_DAY, note_id=None)
    assert not created and e2["sources"] == 2      # yazım her zaman tazeler: çift kayıt oluşmaz


def test_seed_switch_applied_but_response_lost_counts_as_success(dynamo, monkeypatch):
    from agents.storage import dynamo_table

    original, calls = dynamo_table.DynamoTable.put_if, []

    def lost_response(self, item, condition):
        original(self, item, condition)
        calls.append(item["SK"])
        if len(calls) == 1:
            raise dynamo_table.Conflict("yanıt kayboldu, yeniden denendi")

    monkeypatch.setattr(dynamo_table.DynamoTable, "put_if", lost_response)
    book = dynamo.book()
    book.ensure(SEED_DAY)
    meta = _meta()
    assert len(book.entries) == 5 and len(_partition(keys.memory_partition("fake-run", meta["generation"]))) == 5


def test_transaction_conflict_on_single_write_is_retried(dynamo, monkeypatch):
    from botocore.exceptions import ClientError

    from agents.storage import dynamo_table

    err = ClientError({"Error": {"Code": "TransactionConflictException", "Message": "x"}}, "PutItem")
    assert dynamo_table.is_conflict_error(err)
    feed = dynamo.feed()
    feed.add(agent="review", kind="proposal", summary="s", status="awaiting_approval")
    state = {"n": 0}
    real_update = feed.repository.table.table.update_item

    def flaky_update(**kw):
        state["n"] += 1
        if state["n"] == 1:
            raise err
        return real_update(**kw)

    monkeypatch.setattr(feed.repository.table.table, "update_item", flaky_update)
    assert feed.update(1, status="approved")["status"] == "approved" and state["n"] == 2


def test_full_load_keeps_only_recent_log(dynamo, monkeypatch):
    from agents.storage import dynamo_memory_sync

    monkeypatch.setattr(dynamo_memory_sync, "LOG_KEEP", 2)
    book = dynamo.book()
    book.reset(SEED_DAY)
    for d in range(3):
        book.feedback("M00900", True, SEED_DAY + d)
    assert [x["day"] for x in dynamo.book().log] == [SEED_DAY + 1, SEED_DAY + 2]
    assert dynamo.book().get("M00900")["sources"] == 4
