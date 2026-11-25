"""Bedrock modeli. Kimlik çıkarım profili biçiminde olmalı (global. / us. öneki); öneksiz kimlik
"on-demand throughput not supported" hatası verir.

Öncelik: (1) şablonun `model/load.py` dosyası (`agentcore create` üretir; en güncel kimlik orada tutulur),
(2) `CM_AGENT_MODEL_ID` ortam değişkeni, (3) aşağıdaki varsayılan. Kimliği elle yazmadan önce keşfedin:
  aws bedrock list-foundation-models --by-provider Anthropic --query "modelSummaries[?modelLifecycle.status=='ACTIVE'].modelId"
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"
PROFILE_PREFIXES = ("global.", "us.", "eu.", "apac.", "au.", "jp.")


def check_model_id(model_id: str) -> str:
    if not model_id.startswith(PROFILE_PREFIXES):
        raise ValueError(f"Model kimliği çıkarım profili biçiminde olmalı (ör. global.{model_id}); verilen: {model_id}")
    return model_id


def load_model():
    try:                                             # şablonun yükleyicisi varsa onu kullan
        from model.load import load_model as template_loader  # type: ignore

        return template_loader()
    except Exception as e:  # noqa: BLE001 - şablon yoksa ya da imzası farklıysa kendi yükleyicimiz
        from strands.models import BedrockModel

        log.warning("Şablonun model/load.py yükleyicisi kullanılamadı (%s); CM_AGENT_MODEL_ID / varsayılan kullanılıyor.", e)

        return BedrockModel(model_id=check_model_id(os.environ.get("CM_AGENT_MODEL_ID", DEFAULT_MODEL_ID)),
                            region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
