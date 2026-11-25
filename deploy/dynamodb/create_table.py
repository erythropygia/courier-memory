"""Courier Memory DynamoDB tablosunu kurar (idempotent) ve isteğe bağlı mevcut JSON durumunu taşır.

  python deploy/dynamodb/create_table.py [--table courier-memory] [--region eu-central-1] [--migrate] [--print-policy]

- Tablo: tek tablo, PK/SK (string), isteğe bağlı faturalama (PAY_PER_REQUEST), varsayılan sunucu tarafı şifreleme,
  zamana bağlı kurtarma (PITR) açık. Varsa dokunulmaz (yalnız PITR açık olduğu doğrulanır). ACTIVE olana dek beklenir.
- --migrate: data/live_memory.json ve data/agent_feed.json varsa tabloya yükler. O çalıştırmanın hafızası ya da
  akış tabloda zaten varsa atlanır (ikinci çalıştırma bir şey yazmaz).
- app_policy_document(): uygulamanın yalnız bu tabloda ihtiyaç duyduğu DynamoDB eylemleri (diğer dağıtım betikleri
  içe aktarıp çalışma ortamı rolüne ekler). Anahtar düzeni: agents/storage/dynamo_keys.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.storage.config import DEFAULT_TABLE  # noqa: E402
from agents.storage.dynamo_keys import (INITIAL_GENERATION, event_key, feed_meta_key, memory_meta_key,  # noqa: E402
                                        table_definition)

# Uygulamanın kullandığı eylemler. TransactWriteItems'ın ayrı bir IAM eylemi yoktur: içindeki Put/Update adımları
# dynamodb:PutItem / dynamodb:UpdateItem ile yetkilendirilir. BatchWriteItem hem toplu yazım hem eski nesil silme içindir.
APP_ACTIONS = (
    "dynamodb:GetItem",          # META ve tek olay okuma (tutarlı)
    "dynamodb:Query",            # bölüm/aralık okuma (hafıza nesli, LOG aralığı, akış olayları)
    "dynamodb:BatchGetItem",     # değişen hafıza girişlerini yeniden okuma
    "dynamodb:PutItem",          # META geçişi, kullanım kaydı, işlem içi Put adımları
    "dynamodb:UpdateItem",       # akış olayı güncelleme, işlem içi META sürüm artışı
    "dynamodb:BatchWriteItem",   # tohumlama ve eski nesillerin silinmesi
)


PITR_ATTEMPTS = 12


def table_arn(region: str, account: str, table: str) -> str:
    return f"arn:aws:dynamodb:{region}:{account}:table/{table}"


def app_policy_document(arn: str) -> dict:
    """Uygulama (web + AgentCore çalışma ortamları) için en az yetkili IAM politikası: yalnız bu tablo."""
    return {"Version": "2012-10-17",
            "Statement": [{"Sid": "CourierMemoryTable", "Effect": "Allow", "Action": list(APP_ACTIONS), "Resource": [arn]}]}


def ensure_table(client, name: str) -> bool:
    """Tablo yoksa oluşturur; ACTIVE bekler; PITR'yi açar. Döner: yeni oluşturulduysa True."""
    created = False
    try:
        client.describe_table(TableName=name)
    except client.exceptions.ResourceNotFoundException:
        try:
            client.create_table(**table_definition(name))
            created = True
        except client.exceptions.ResourceInUseException:
            pass                                   # aynı anda başka biri oluşturdu
    client.get_waiter("table_exists").wait(TableName=name, WaiterConfig={"Delay": 2, "MaxAttempts": 60})
    enable_pitr(client, name)
    return created


def enable_pitr(client, name: str, attempts: int = PITR_ATTEMPTS, delay: float = 5.0) -> None:
    """Yeni tabloda yedekleme altyapısı birkaç saniye hazır olmayabilir: ContinuousBackupsUnavailable'da yeniden dener."""
    for i in range(attempts):
        try:
            client.update_continuous_backups(TableName=name,
                                             PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True})
            return
        except client.exceptions.ContinuousBackupsUnavailableException:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def migrate_memory(t, doc: dict | None) -> tuple[int, int]:
    """live_memory.json → yeni nesil bölümü + META (yalnız o çalıştırmanın META'sı yoksa). Döner: (giriş, günlük)."""
    from agents.storage.dynamo_memory_seed import meta_item, new_generation, purge
    from agents.storage.dynamo_memory_sync import entry_item, log_item
    from agents.storage.dynamo_table import Conflict, encode

    if not doc or not doc.get("run_id") or t.get(memory_meta_key(doc["run_id"])) is not None:
        return 0, 0
    run_id, gen = doc["run_id"], new_generation()
    entries, logs = doc.get("entries", []), doc.get("log", [])
    t.batch_put(entry_item(run_id, gen, e, i) for i, e in enumerate(entries))
    t.batch_put(log_item(run_id, gen, v, rec) for v, rec in enumerate(logs, start=1))
    meta = {**meta_item(run_id, gen, doc.get("seed_day"), len(entries), None), **encode({"version": len(logs)})}
    try:
        t.put_if(meta, "attribute_not_exists(PK)")
    except Conflict:                       # başka bir süreç aynı anda tohumladı: yüklediklerimizi geri al
        purge(t, run_id, gen)
        return 0, 0
    return len(entries), len(logs)


def migrate_feed(t, doc: dict | None) -> int:
    from agents.storage.dynamo_table import Conflict, encode

    events = (doc or {}).get("events", [])
    if not events or t.get(feed_meta_key()) is not None:
        return 0
    t.batch_put({**encode(o), **event_key(INITIAL_GENERATION, int(o["n"]))} for o in events)
    try:
        t.put_if({**feed_meta_key(), "generation": INITIAL_GENERATION, "seq": max(int(o["n"]) for o in events)},
                 "attribute_not_exists(PK)")
    except Conflict:
        return 0
    return len(events)


def migrate(table: str, region: str | None, data_dir: Path) -> dict:
    from agents.storage.dynamo_table import DynamoTable

    t = DynamoTable(table, region)
    entries, logs = migrate_memory(t, _read_json(data_dir / "live_memory.json"))
    return {"memory_entries": entries, "memory_log": logs, "feed_events": migrate_feed(t, _read_json(data_dir / "agent_feed.json"))}


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Courier Memory DynamoDB tablosu (idempotent kurulum + taşıma)")
    ap.add_argument("--table", default=os.environ.get("CM_DYNAMODB_TABLE") or DEFAULT_TABLE)
    ap.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
    ap.add_argument("--migrate", action="store_true", help="data/live_memory.json ve data/agent_feed.json'u yükle")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--print-policy", action="store_true", help="uygulama için en az yetkili IAM politikasını yazdır")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    a = _parse(argv)
    try:
        client = boto3.client("dynamodb", region_name=a.region)
        created = ensure_table(client, a.table)
        region = client.meta.region_name
        status = sys.stderr if a.print_policy else sys.stdout   # --print-policy: stdout yalnız JSON (dosyaya yönlendirilebilir)
        print(f"Tablo hazır: {a.table} ({region}; {'oluşturuldu' if created else 'zaten vardı'}; PITR açık)", file=status)
        if a.migrate:
            out = migrate(a.table, region, a.data_dir)
            print("Taşındı: " + ", ".join(f"{k}={v}" for k, v in out.items()), file=status)
        if a.print_policy:
            account = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
            print(json.dumps(app_policy_document(table_arn(region, account, a.table)), indent=2))
        return 0
    except (ClientError, BotoCoreError) as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
