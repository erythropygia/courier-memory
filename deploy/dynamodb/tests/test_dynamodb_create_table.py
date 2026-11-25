"""DynamoDB tablo kurulumu, taşıma ve en az yetki politikası (moto; gerçek AWS'ye gidilmez)."""
import json
import sys
from pathlib import Path

import boto3
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from create_table import APP_ACTIONS, app_policy_document, ensure_table, main, migrate  # noqa: E402

REGION = "eu-central-1"
FAKE_ENV = {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION}


@pytest.fixture
def aws(monkeypatch):
    from moto import mock_aws

    for k, v in FAKE_ENV.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        yield boto3.client("dynamodb", region_name=REGION)


def test_ensure_table_is_idempotent_with_on_demand_and_pitr(aws):
    assert ensure_table(aws, "cm-x") is True
    assert ensure_table(aws, "cm-x") is False
    t = aws.describe_table(TableName="cm-x")["Table"]
    assert t["TableStatus"] == "ACTIVE" and t["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
    assert {k["AttributeName"]: k["KeyType"] for k in t["KeySchema"]} == {"PK": "HASH", "SK": "RANGE"}
    pitr = aws.describe_continuous_backups(TableName="cm-x")["ContinuousBackupsDescription"]
    assert pitr["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"] == "ENABLED"


def test_migrate_uploads_memory_and_feed(aws, tmp_path, monkeypatch):
    ensure_table(aws, "cm-x")
    mem = {"app_data": True, "run_id": "run-1", "seed_day": 12,
           "entries": [{"id": "M00001", "address": 4, "kind": "bell", "text": "t", "sources": 2, "status": "active",
                        "ttl_until": None, "updated_at": 1700000000.5}],
           "log": [{"operation": "updated", "record": "M00001", "day": 12}]}
    (tmp_path / "live_memory.json").write_text(json.dumps(mem), encoding="utf-8")
    (tmp_path / "agent_feed.json").write_text(json.dumps({"events": [{"n": 1, "agent": "review", "type": "report",
                                                                     "summary": "s", "status": "info", "time": 1.5}]}), encoding="utf-8")
    monkeypatch.setenv("CM_DYNAMODB_TABLE", "cm-x")
    monkeypatch.setenv("CM_STORAGE", "dynamodb")
    out = migrate("cm-x", REGION, tmp_path)
    assert out == {"memory_entries": 1, "memory_log": 1, "feed_events": 1}
    assert migrate("cm-x", REGION, tmp_path) == {"memory_entries": 0, "memory_log": 0, "feed_events": 0}   # tekrar: atlanır

    from agents.feed import AgentFeed
    from agents.memorybook import MemoryBook
    from agents.tests.storage_support import FakeRun

    book = MemoryBook(FakeRun(run_id="run-1"))
    assert book.seed_day == 12 and book.get("M00001")["sources"] == 2 and len(book.log) == 1
    assert book.get("M00001")["updated_at"] == 1700000000.5
    assert AgentFeed().items()[0]["summary"] == "s" and AgentFeed().add(agent="a", kind="b", summary="c")["n"] == 2


def test_migrate_without_files_is_noop(aws, tmp_path):
    ensure_table(aws, "cm-x")
    assert migrate("cm-x", REGION, tmp_path) == {"memory_entries": 0, "memory_log": 0, "feed_events": 0}


def test_policy_is_least_privilege_on_one_table():
    doc = app_policy_document("arn:aws:dynamodb:eu-central-1:123456789012:table/courier-memory")
    assert doc["Version"] == "2012-10-17" and len(doc["Statement"]) == 1
    st = doc["Statement"][0]
    assert st["Effect"] == "Allow" and st["Resource"] == ["arn:aws:dynamodb:eu-central-1:123456789012:table/courier-memory"]
    assert sorted(st["Action"]) == sorted(APP_ACTIONS) and not any("*" in a for a in st["Action"])
    assert set(APP_ACTIONS) == {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query",
                                "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem"}


def test_policy_from_parts():
    from create_table import table_arn

    assert table_arn("eu-central-1", "123456789012", "t") == "arn:aws:dynamodb:eu-central-1:123456789012:table/t"


def test_main_creates_and_prints_policy(aws, capsys):
    assert main(["--table", "cm-y", "--region", REGION, "--print-policy"]) == 0
    out = capsys.readouterr().out
    assert "cm-y" in out and json.loads(out[out.index("{"):])["Statement"][0]["Resource"][0].endswith(":table/cm-y")


def test_enable_pitr_retries_while_backups_unavailable():
    from create_table import enable_pitr

    class Unavailable(Exception):
        pass

    class FakeClient:
        class exceptions:
            ContinuousBackupsUnavailableException = Unavailable

        calls = 0

        def update_continuous_backups(self, **kw):
            FakeClient.calls += 1
            if FakeClient.calls < 3:
                raise Unavailable()

    enable_pitr(FakeClient(), "t", delay=0)
    assert FakeClient.calls == 3
