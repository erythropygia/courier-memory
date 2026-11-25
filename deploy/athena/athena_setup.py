"""Athena kurulumu: demo verisini S3'e JSON Lines olarak yükler, Glue veritabanı ve tablolarını Athena DDL ile tanımlar.

  AWS_PROFILE=hackathon AWS_REGION=us-east-1 python deploy/athena/athena_setup.py [--run-dir data/demo_run]

Kurulan kaynaklar (tekrar çalıştırmak güvenlidir; tablolar yeniden tanımlanır, veri üzerine yazılır):
  S3 bucket   courier-memory-athena-<hesap>-<bölge>   data/<tablo>/part-0.json.gz · results/ (sorgu sonuçları)
  Çalışma grubu  courier-memory   sonuç yeri zorunlu, sorgu başına en çok 100 MB tarama
  Veritabanı  courier_memory      deliveries · addresses · daily_metrics · couriers

Kişisel veri yüklenmez: kurye adı alınmaz, serbest metin kurye notları (notes.json) hiç yüklenmez.
Adlar deploy/agentcore/agentcore_config.py ve runtime/cm/athena.py ile aynıdır (Analiz Ajanı'nın izinleri bunlara göre).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path

DATABASE = "courier_memory"
WORKGROUP = "courier-memory"
BUCKET_PREFIX = "courier-memory-athena-"
SCAN_LIMIT_BYTES = 100 * 1024 * 1024
FAIL_REASONS = ("recipient_absent", "address_not_found", "closed", "entry_failed", "recipient_unreachable", "wrong_deferral", "other")

_DAILY = [("arm", "string"), ("arm_label", "string"), ("day", "int"), ("weekday", "int"), ("shipments", "int"),
          ("deferred", "int"), ("attempted", "int"), ("ok", "int"), ("fail", "int"), ("first_attempt_rate", "double"),
          ("preventable_fail", "int"), *[(f"fail_{r}", "int") for r in FAIL_REASONS], ("couriers", "int"), ("km", "double"),
          ("minutes_mean", "double"), ("in_band", "int"), ("in_band_share", "double"), ("in_band_planned_share", "double"),
          ("planned_cv", "double"), ("overtime_minutes", "double"), ("departure_mean", "double"), ("end_mean", "double"),
          ("workload_cv", "double"), ("door_minutes_per_stop", "double"), ("stops", "int"), ("unfamiliar_share", "double"),
          ("hinted_stops", "int"), ("hint_helped", "int"), ("wrong_hint", "int"), ("memory_coverage", "double"), ("notes", "int"),
          ("window_hits", "int"), ("window_wait_minutes", "double"), ("wasted_trips", "int"), ("plan_deferred_stops", "int"),
          ("revisit_stops", "int"), ("wrong_deferrals", "int"), ("eta_abs_error", "double")]

TABLES = {
    "deliveries": {"comment": "Hafızalı yapının (kol D) her teslim denemesi; minute = günün dakikası, absent = 1 alıcı yoktu",
                   "columns": [("day", "int"), ("address_id", "int"), ("minute", "int"), ("absent", "int")]},
    "addresses": {"comment": "Adresler: konum, tür, harita bloğu",
                  "columns": [("id", "int"), ("lat", "double"), ("lng", "double"), ("kind", "string"), ("block", "int"), ("label", "string")]},
    "daily_metrics": {"comment": "Günlük şube ölçüleri, dört yapı (A-D) yan yana", "columns": _DAILY},
    "couriers": {"comment": "Kurye kimliği ve türü (isim yok)",
                 "columns": [("id", "string"), ("kind", "string"), ("start_day", "int"), ("end_day", "int"), ("leave_day_count", "int")]},
}


def _load(run: Path, name: str) -> dict:
    return json.loads((run / name).read_text(encoding="utf-8"))


def _ordered(table: str, values: dict) -> dict:
    return {c: values.get(c) for c, _ in TABLES[table]["columns"]}


def build_rows(table: str, run: Path) -> Iterator[dict]:
    """Tablonun satırları, sütun sırasıyla. Saf: yalnız run klasörünü okur."""
    if table == "deliveries":
        d = _load(run, "delivery_log.json")
        for day, addr, minute, absent in zip(d["day"], d["address"], d["minute"], d["absent"]):
            yield _ordered(table, {"day": day, "address_id": addr, "minute": minute, "absent": absent})
    elif table == "addresses":
        d = _load(run, "addresses.json")
        for row in d["addresses"]:
            yield _ordered(table, dict(zip(d["fields"], row)) | {"id": row[d["fields"].index("id")]})
    elif table == "daily_metrics":
        labels = _load(run, "meta.json")["arms"]
        for arm, rows in _load(run, "daily.json")["arms"].items():
            for r in rows:
                reasons = {f"fail_{k}": (r.get("fail_by_reason") or {}).get(k, 0) for k in FAIL_REASONS}
                yield _ordered(table, {**r, **reasons, "arm": arm, "arm_label": labels.get(arm)})
    elif table == "couriers":
        for c in _load(run, "couriers.json")["couriers"]:
            yield _ordered(table, {"id": c["id"], "kind": c.get("kind"), "start_day": c.get("start_day"),
                                   "end_day": c.get("end_day"), "leave_day_count": len(c.get("leave_days") or [])})
    else:
        raise KeyError(table)


def create_table_sql(table: str, database: str, bucket: str) -> str:
    spec = TABLES[table]
    cols = ",\n  ".join(f"`{c}` {t}" for c, t in spec["columns"])
    return (f"CREATE EXTERNAL TABLE IF NOT EXISTS {database}.{table} (\n  {cols}\n)\n"
            f"COMMENT '{spec['comment']}'\n"
            "ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'\n"
            f"LOCATION 's3://{bucket}/data/{table}/'")


def _jsonl_gz(rows: Iterator[dict]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
    return buf.getvalue()


# ------------------------------------------------------------------ AWS
def _ensure_bucket(s3, bucket: str, region: str) -> None:
    from botocore.exceptions import ClientError

    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise
    kw = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
    s3.create_bucket(Bucket=bucket, **kw)
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    print(f"  bucket oluşturuldu: {bucket}")


def _ensure_workgroup(athena, bucket: str) -> None:
    cfg = {"ResultConfiguration": {"OutputLocation": f"s3://{bucket}/results/"}, "EnforceWorkGroupConfiguration": True,
           "PublishCloudWatchMetricsEnabled": True, "BytesScannedCutoffPerQuery": SCAN_LIMIT_BYTES}
    names = {w["Name"] for w in athena.list_work_groups()["WorkGroups"]}
    if WORKGROUP in names:
        athena.update_work_group(WorkGroup=WORKGROUP, ConfigurationUpdates={
            "ResultConfigurationUpdates": cfg["ResultConfiguration"], "EnforceWorkGroupConfiguration": True,
            "PublishCloudWatchMetricsEnabled": True, "BytesScannedCutoffPerQuery": SCAN_LIMIT_BYTES})
    else:
        athena.create_work_group(Name=WORKGROUP, Configuration=cfg, Description="Courier Memory Analiz Ajanı (salt okunur SQL)")
        print(f"  çalışma grubu oluşturuldu: {WORKGROUP}")


def _run(athena, sql: str, database: str | None = None) -> list[list[str]]:
    kw = {"QueryExecutionContext": {"Database": database}} if database else {}
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP, **kw)["QueryExecutionId"]
    for _ in range(120):
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] == "SUCCEEDED":
            rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
            return [[d.get("VarCharValue") for d in r["Data"]] for r in rows]
        if st["State"] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena: {st.get('StateChangeReason')}\n{sql}")
        time.sleep(1)
    raise TimeoutError(sql)


def main(argv: list[str] | None = None) -> int:
    import boto3

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", default=str(Path(__file__).resolve().parents[2] / "data" / "demo_run"))
    args = ap.parse_args(argv)
    run = Path(args.run_dir)

    session = boto3.Session()
    region = session.region_name or "us-east-1"
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"{BUCKET_PREFIX}{account}-{region}"
    s3, athena = session.client("s3", region_name=region), session.client("athena", region_name=region)
    print(f"==> Athena kurulumu: hesap {account}, bölge {region}, bucket {bucket}")

    _ensure_bucket(s3, bucket, region)
    _ensure_workgroup(athena, bucket)
    for table in TABLES:
        body = _jsonl_gz(build_rows(table, run))
        s3.put_object(Bucket=bucket, Key=f"data/{table}/part-0.json.gz", Body=body, ServerSideEncryption="AES256")
        print(f"  yüklendi: data/{table}/ ({len(body) // 1024} KB sıkıştırılmış)")
    _run(athena, f"CREATE DATABASE IF NOT EXISTS {DATABASE} COMMENT 'Courier Memory geçmiş teslim verisi'")
    for table in TABLES:
        _run(athena, f"DROP TABLE IF EXISTS {DATABASE}.{table}")              # yalnız tanım; S3'teki veri yerinde kalır
        _run(athena, create_table_sql(table, DATABASE, bucket))
        n = _run(athena, f"SELECT count(*) FROM {table}", DATABASE)[1][0]
        print(f"  tablo {DATABASE}.{table}: {n} satır")
    print("Hazır. Analiz Ajanı (analyst runtime) bu tabloları sorgular.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
