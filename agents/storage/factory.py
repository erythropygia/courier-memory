"""Ortama göre depo üretimi. DynamoDB modülleri (ve boto3) yalnız CM_STORAGE=dynamodb iken içe aktarılır."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import FeedRepository, MemoryRepository, UsageSink
from .config import StorageConfig, load_config
from .file_feed import FileFeedRepository
from .file_memory import FileMemoryRepository
from .file_usage import FileUsageSink


def _table(cfg: StorageConfig):
    from .dynamo_table import DynamoTable

    return DynamoTable(cfg.table, cfg.region)


def memory_repository(run_id: str, path: Path, cfg: StorageConfig | None = None) -> MemoryRepository:
    cfg = cfg or load_config()
    if not cfg.is_dynamodb:
        return FileMemoryRepository(path, run_id)
    from .dynamo_memory import DynamoMemoryRepository

    return DynamoMemoryRepository(_table(cfg), run_id, cfg.sync_seconds)


def feed_repository(path: Path, max_events: Callable[[], int], cfg: StorageConfig | None = None) -> FeedRepository:
    cfg = cfg or load_config()
    if not cfg.is_dynamodb:
        return FileFeedRepository(path, max_events)
    from .dynamo_feed import DynamoFeedRepository

    return DynamoFeedRepository(_table(cfg), max_events)


def usage_sinks(path: Path, cfg: StorageConfig | None = None) -> tuple[UsageSink, ...]:
    """Dosya günlüğü her modda yazılır; dynamodb modunda tabloya da yazılır."""
    cfg = cfg or load_config()
    if not cfg.is_dynamodb:
        return (FileUsageSink(path),)
    from .dynamo_usage import DynamoUsageSink

    return (FileUsageSink(path), DynamoUsageSink(_table(cfg)))
