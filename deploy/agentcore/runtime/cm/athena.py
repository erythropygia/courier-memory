"""Analiz Ajanı'nın aracı: geçmiş teslim verisine Amazon Athena ile salt okunur SQL.

Tablolar deploy/athena/athena_setup.py ile kurulur (veritabanı `courier_memory`, çalışma grubu `courier-memory`).
Koruma üç katmanlı: (1) burada yalnız tek bir SELECT/WITH kabul edilir ve satır sayısı sınırlanır, (2) çalışma grubu
sorgu başına taranan veriyi sınırlar ve sonuç yerini zorlar, (3) runtime rolü yalnız okuma + sonuç klasörüne yazma izni taşır.
Kurye notları (serbest metin, kişisel veri olabilir) Athena'ya hiç yüklenmez.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import lru_cache

from strands import tool

log = logging.getLogger(__name__)

DATABASE_ENV, WORKGROUP_ENV = "CM_ATHENA_DATABASE", "CM_ATHENA_WORKGROUP"
DEFAULT_DATABASE, DEFAULT_WORKGROUP = "courier_memory", "courier-memory"
MAX_ROWS = 200
TIMEOUT_S = 60
POLL_S = 1.0

SCHEMA = """Tablolar (veritabanı courier_memory; simülasyonun 40 günlük geçmişi, kişisel veri yok):
- deliveries(day int, address_id int, minute int, absent int): hafızalı yapının (kol D) her teslim denemesi; minute = günün dakikası, absent = 1 alıcı yoktu.
- addresses(id int, lat double, lng double, kind string, block int, label string): adresler; kind = house/apartment/site/shop…, block = harita bloğu.
- daily_metrics(arm string, arm_label string, day int, weekday int, shipments int, attempted int, ok int, fail int, first_attempt_rate double,
  preventable_fail int, fail_recipient_absent int, fail_address_not_found int, fail_closed int, fail_entry_failed int, fail_recipient_unreachable int,
  fail_wrong_deferral int, fail_other int, couriers int, km double, minutes_mean double, overtime_minutes double, unfamiliar_share double,
  hinted_stops int, hint_helped int, wrong_hint int, memory_coverage double, notes int, wasted_trips int, eta_abs_error double, …):
  günlük şube ölçüleri; arm A = mevcut yapı (sabit bölge), B = geçmişe bakmadan atama, C = çekirdek bölgeli dinamik plan, D = çekirdek bölge + hafıza.
- couriers(id string, kind string, start_day int, end_day int, leave_day_count int): kurye kimliği ve türü (senior/regular/new…), isim yok."""

_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.I)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|merge|drop|create|alter|unload|msck|grant|revoke|call|prepare|execute|"
                        r"deallocate|vacuum|optimize|show|describe|explain|use|set|reset|refresh)\b", re.I)
_OTHER_DB = re.compile(r"\b(from|join)\s+[\"`]?(\w+)[\"`]?\s*\.", re.I)


class QueryRejected(ValueError):
    """Sorgu güvenlik kuralına uymuyor; model düzeltip yeniden deneyebilir."""


class QueryFailed(RuntimeError):
    """Athena sorguyu çalıştıramadı (SQL hatası, zaman aşımı, izin)."""


def _database() -> str:
    return os.environ.get(DATABASE_ENV, DEFAULT_DATABASE)


def validate_sql(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise QueryRejected("Boş sorgu.")
    if ";" in s or "--" in s or "/*" in s:
        raise QueryRejected("Tek bir SELECT yazın; noktalı virgül ve yorum kullanılamaz.")
    if not _ALLOWED_START.match(s):
        raise QueryRejected("Yalnız SELECT (ya da WITH … SELECT) sorgusu çalıştırılabilir.")
    bad = _FORBIDDEN.search(s)
    if bad:
        raise QueryRejected(f"'{bad.group(1)}' kullanılamaz: yalnız SELECT ile okuma yapılır.")
    other = [m.group(2) for m in _OTHER_DB.finditer(s) if m.group(2).lower() != _database().lower()]
    if other:
        raise QueryRejected(f"Yalnız {_database()} veritabanının tabloları sorgulanabilir ({other[0]} değil).")
    return f"SELECT * FROM ({s}) AS q LIMIT {MAX_ROWS}"


@lru_cache(maxsize=1)
def _client():
    import boto3

    return boto3.client("athena", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))


def run_query(sql: str, client=None, sleep=time.sleep, now=time.monotonic) -> dict:
    q = validate_sql(sql)
    c = client or _client()
    qid = c.start_query_execution(QueryString=q, QueryExecutionContext={"Database": _database()},
                                  WorkGroup=os.environ.get(WORKGROUP_ENV, DEFAULT_WORKGROUP))["QueryExecutionId"]
    deadline = now() + TIMEOUT_S
    while True:
        ex = c.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = ex["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise QueryFailed(f"Sorgu çalışmadı: {ex['Status'].get('StateChangeReason') or state}")
        if now() > deadline:
            c.stop_query_execution(QueryExecutionId=qid)
            raise QueryFailed(f"Sorgu {TIMEOUT_S} sn süre sınırını aştı ve durduruldu; daha dar bir sorgu yazın.")
        sleep(POLL_S)
    rows = c.get_query_results(QueryExecutionId=qid, MaxResults=MAX_ROWS + 1)["ResultSet"]["Rows"]
    values = [[d.get("VarCharValue") for d in r["Data"]] for r in rows]
    header, data = (values[0], values[1:]) if values else ([], [])
    scanned = (ex.get("Statistics") or {}).get("DataScannedInBytes", 0)
    return {"columns": header, "rows": data, "row_count": len(data), "truncated": len(data) >= MAX_ROWS,
            "scanned_kb": round(scanned / 1024, 1)}


@tool
def query_history(sql: str) -> str:
    """Geçmiş teslim verisine salt okunur SQL (Amazon Athena, Presto/Trino söz dizimi). Yalnız tek bir SELECT;
    en çok 200 satır döner. Tablolar: deliveries, addresses, daily_metrics, couriers (şema sistem isteminde).

    Args:
        sql: Tek bir SELECT ya da WITH … SELECT sorgusu; noktalı virgül ve yorum yok.
    """
    try:
        return json.dumps(run_query(sql), ensure_ascii=False)
    except QueryRejected as e:
        return json.dumps({"error": str(e), "hint": "Yalnız tek bir SELECT yazın."}, ensure_ascii=False)
    except QueryFailed as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 - AWS istemci hatası: ayrıntı log'a, modele kısa ve güvenli mesaj
        log.exception("Athena sorgusu başarısız")
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        return json.dumps({"error": f"Athena'ya şu an ulaşılamıyor ({code})."}, ensure_ascii=False)
