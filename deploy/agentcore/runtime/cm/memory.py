"""AgentCore Memory: kısa süreli (oturum olayları) ve uzun süreli (kullanıcı başına olgular) konuşma hafızası.

`agentcore create --template agent-python-strands` projede `agentMemory` adlı hafızayı (SEMANTIC + EPISODIC) tanımlar;
`agentcore deploy` kimliğini çalışma ortamına `MEMORY_AGENTMEMORY_ID` olarak verir. Değişken yoksa (yerel deneme, test)
oturum yöneticisi kurulmaz ve ajan hafızasız çalışır.

Ad alanları `actorId` ile ayrılır: bir kuryenin konuşma olguları başka kuryeye gelmez.
Bu, şubenin adres hafızasından (agents/memorybook.py) ayrıdır: o adresi anlatır, bu konuşmayı hatırlar.
"""
from __future__ import annotations

import os

MEMORY_ENV = "MEMORY_AGENTMEMORY_ID"
FACTS_TOP_K = 5                      # kurye başına olgular: istekte en çok kaç kayıt geri çağrılır
FACTS_NAMESPACE = "/users/{actorId}/facts"
EPISODES_NAMESPACE = "/episodes/{actorId}/{sessionId}"


def session_manager(actor_id: str, session_id: str):
    memory_id = os.environ.get(MEMORY_ENV)
    if not memory_id:
        return None
    from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
    from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

    cfg = AgentCoreMemoryConfig(
        memory_id=memory_id, session_id=session_id, actor_id=actor_id,
        retrieval_config={FACTS_NAMESPACE: RetrievalConfig(top_k=FACTS_TOP_K, relevance_score=0.0),
                          EPISODES_NAMESPACE: RetrievalConfig(top_k=3, relevance_score=0.0)})
    return AgentCoreMemorySessionManager(cfg, region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
