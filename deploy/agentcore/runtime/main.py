"""Courier Memory · AgentCore Runtime giriş noktası.

Kurallar (AgentCore Runtime dağıtımı):
- `bedrock_agentcore.runtime` içe aktarılır (kökten değil): soğuk başlangıç 30 sn sınırını aşmasın.
- Ajan tembel kurulur (`_get_agent`): model, alan servisleri ve hafıza ilk istekte yüklenir.
- İşleyici `@app.entrypoint` ile süslü, akış döndüren asenkron üreteçtir; gövdeden `prompt` ve `actorId` okunur.
- `app.run()` yalnız `__main__` altında.

Yerel deneme (proje klasöründen):  agentcore dev --port 8081
  agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünkü brifingim?","actorId":"O02"}'
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from cm.payload import parse_request

app = BedrockAgentCoreApp()
_model = None
_agents: dict[tuple[str, str], object] = {}


def _get_model():
    global _model
    if _model is None:
        from cm.model import load_model

        _model = load_model()
    return _model


def _get_agent(actor_id: str, session_id: str):
    """Kimlik + oturum başına bir ajan: sistem istemi kimliği söyler, kanca kimlik sınırını zorlar, hafıza ad alanı ayrılır."""
    key = (actor_id, session_id)
    if key not in _agents:
        from strands import Agent

        from cm.memory import session_manager
        from cm.prompt import build_system_prompt
        from cm.roles import agent_role, tools_for
        from cm.scope import CourierScope
        from cm.backend import backend, role_of

        role = role_of(actor_id)
        me = agent_role()                      # bu runtime: supervisor | planner | courier | memory_keeper | all
        name = backend().courier_name(actor_id) if role == "courier" else None
        _agents[key] = Agent(model=_get_model(), tools=tools_for(me, actor_id, session_id),
                             system_prompt=build_system_prompt(actor_id, role, name, agent_role=me),
                             hooks=[CourierScope(actor_id)], session_manager=session_manager(actor_id, session_id),
                             callback_handler=None, name=f"courier-memory-{me}",
                             trace_attributes={"cm.agent_role": me, "cm.actor_role": role, "cm.actor_id": actor_id,
                                               "cm.toolset": backend().name})
    return _agents[key]


@app.entrypoint
async def invoke(payload, context):
    req = parse_request(payload)
    if not req.prompt:
        yield {"error": "İstek gövdesinde `prompt` yok."}
        return
    session_id = getattr(context, "session_id", None) or "local-session"
    try:
        agent = _get_agent(req.actor_id, session_id)
        async for event in agent.stream_async(req.prompt):
            if isinstance(event, dict) and "event" in event:      # ham model akışı: JSON'a çevrilebilir tek olay türü
                yield {"event": event["event"]}
    except Exception as e:  # noqa: BLE001 - hata akışa yazılır; çağıran boş yanıt yerine nedeni görür
        yield {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    app.run()
