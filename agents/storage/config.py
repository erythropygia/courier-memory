"""Depolama arka ucu seçimi (ortam değişkenleri).

  CM_STORAGE               file (varsayılan; JSON dosyaları, bugünkü davranış) | dynamodb
  CM_DYNAMODB_TABLE        tablo adı (varsayılan courier-memory)
  AWS_REGION / AWS_DEFAULT_REGION   bölge (yoksa boto3'ün kendi çözümlemesi: ~/.aws/config)
  CM_DYNAMODB_SYNC_SECONDS hafıza önbelleğinin sürüm kontrolü aralığı (varsayılan 0 = her okumada kontrol)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

BACKENDS = ("file", "dynamodb")
DEFAULT_TABLE = "courier-memory"


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "file"
    table: str = DEFAULT_TABLE
    region: str | None = None
    sync_seconds: float = 0.0

    @property
    def is_dynamodb(self) -> bool:
        return self.backend == "dynamodb"


def load_config(env: Mapping[str, str] | None = None) -> StorageConfig:
    env = os.environ if env is None else env
    backend = (env.get("CM_STORAGE") or "file").strip().lower()
    if backend not in BACKENDS:
        raise ValueError(f"CM_STORAGE geçersiz: {backend} (izinli: {', '.join(BACKENDS)})")
    try:
        sync = float(env.get("CM_DYNAMODB_SYNC_SECONDS") or 0)
    except ValueError as e:
        raise ValueError("CM_DYNAMODB_SYNC_SECONDS sayı olmalı") from e
    return StorageConfig(backend=backend, table=(env.get("CM_DYNAMODB_TABLE") or DEFAULT_TABLE).strip(),
                         region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or None, sync_seconds=max(sync, 0.0))
