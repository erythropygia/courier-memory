"""Token kullanım günlüğü: DynamoDB'ye istek başına bir öğe (PK USAGE#{gün}; günlük maliyet tek sorguyla okunur)."""
from __future__ import annotations

import time
import uuid

from .dynamo_keys import usage_key
from .dynamo_table import DynamoTable, encode


class DynamoUsageSink:
    def __init__(self, table: DynamoTable):
        self.table = table

    def record(self, row: dict) -> None:
        stamp = row.get("t") or time.strftime("%Y-%m-%dT%H:%M:%S")
        key = usage_key(stamp[:10], stamp, str(row.get("agent", "-")), uuid.uuid4().hex[:8])
        self.table.table.put_item(Item={**encode(row), **key})
