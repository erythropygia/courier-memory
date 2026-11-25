"""Arka uç seçimi (CM_STORAGE) ve token kullanım günlüğü (dosya + DynamoDB; günlük hatası model çağrısını bozmaz)."""
import json
import logging

import boto3
import pytest
from boto3.dynamodb.conditions import Key

from agents.llm import LLM
from agents.storage import load_config
from agents.storage.file_usage import FileUsageSink
from agents.tests.storage_support import TEST_REGION, TEST_TABLE, moto_table

USAGE = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 1}


def test_default_backend_is_file(monkeypatch):
    for k in ("CM_STORAGE", "CM_DYNAMODB_TABLE", "AWS_REGION", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config()
    assert (cfg.backend, cfg.table, cfg.region) == ("file", "courier-memory", None)


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("CM_STORAGE", "DynamoDB")
    monkeypatch.setenv("CM_DYNAMODB_TABLE", "t1")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    cfg = load_config()
    assert (cfg.backend, cfg.table, cfg.region) == ("dynamodb", "t1", "eu-west-1")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    assert load_config().region == "eu-central-1"


@pytest.mark.parametrize("value", ["s3", "json", ""])
def test_unknown_backend_rejected(monkeypatch, value):
    monkeypatch.setenv("CM_STORAGE", value)
    if value == "":
        assert load_config().backend == "file"
        return
    with pytest.raises(ValueError, match="CM_STORAGE"):
        load_config()


def _live_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    return LLM(mode="live", model="m1")


def test_file_mode_appends_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_STORAGE", "file")
    llm = _live_llm(monkeypatch, tmp_path)
    llm._log_usage("memory", USAGE, 1.234)
    row = json.loads((tmp_path / "usage.jsonl").read_text(encoding="utf-8"))
    assert row["agent"] == "memory" and row["model"] == "m1" and row["seconds"] == 1.23 and row["input_tokens"] == 10


def test_mock_mode_logs_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    LLM(mode="mock")._log_usage("memory", USAGE, 1.0)
    assert not (tmp_path / "usage.jsonl").exists()


def test_dynamodb_mode_writes_file_and_table(monkeypatch, tmp_path):
    with moto_table(monkeypatch):
        llm = _live_llm(monkeypatch, tmp_path)
        llm._log_usage("briefing", USAGE, 2.0)
        items = boto3.resource("dynamodb", region_name=TEST_REGION).Table(TEST_TABLE).scan()["Items"]
        assert len(items) == 1 and items[0]["PK"].startswith("USAGE#") and items[0]["agent"] == "briefing"
        assert items[0]["output_tokens"] == 5 and items[0]["SK"].split("#")[1] == "briefing"
        pk = items[0]["PK"]
        q = boto3.resource("dynamodb", region_name=TEST_REGION).Table(TEST_TABLE).query(KeyConditionExpression=Key("PK").eq(pk))
        assert q["Count"] == 1
    assert (tmp_path / "usage.jsonl").exists()


class _Broken:
    def record(self, row):
        raise RuntimeError("disk full")


def test_logging_failure_never_breaks_the_call(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("CM_STORAGE", "file")
    llm = _live_llm(monkeypatch, tmp_path)
    llm.usage_sinks = (_Broken(), FileUsageSink(tmp_path / "usage.jsonl"))
    with caplog.at_level(logging.WARNING, logger="agents.llm"):
        llm._log_usage("memory", USAGE, 1.0)
    assert "disk full" in caplog.text and (tmp_path / "usage.jsonl").exists()

