"""Çalışma durumu depolama katmanı: canlı hafıza, ajan akışı, token kullanım günlüğü.

CM_STORAGE=file (varsayılan) JSON dosyalarını kullanır; CM_STORAGE=dynamodb tek bir DynamoDB tablosunu
(CM_DYNAMODB_TABLE, varsayılan courier-memory) birden çok sürecin (web uygulaması + AgentCore çalışma ortamları)
eşzamanlı ve tutarlı paylaşacağı biçimde kullanır. Anahtar düzeni: agents/storage/dynamo_keys.py.
"""
from .base import MemoryState, Mutation, StorageConflictError
from .config import BACKENDS, DEFAULT_TABLE, StorageConfig, load_config
from .factory import feed_repository, memory_repository, usage_sinks

__all__ = ["BACKENDS", "DEFAULT_TABLE", "MemoryState", "Mutation", "StorageConfig", "StorageConflictError",
           "feed_repository", "load_config", "memory_repository", "usage_sinks"]
