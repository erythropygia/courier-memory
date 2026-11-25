"""Amazon Quick → Courier Memory köprüsü (AgentCore Gateway'in Lambda hedefi).

Quick bir MCP aracı çağırır (`ask_courier_memory`); Gateway çağrıyı bu Lambda'ya iletir; Lambda soruyu supervisor
runtime'ına (`agent`) gönderir ve metin cevabı döndürür. Supervisor işi uzman ajanlara dağıtır.

Kimlik olaydan alınmaz: her çağrı `QUICK_ACTOR_ID` (varsayılan MUDUR-QUICK) kimliğiyle gider; Quick ya da model değiştiremez.
Ortam: SUPERVISOR_RUNTIME_ARN (zorunlu), QUICK_ACTOR_ID.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from functools import lru_cache

log = logging.getLogger()
log.setLevel(logging.INFO)

TOOL_NAME = "ask_courier_memory"
MAX_QUESTION = 2000
READ_TIMEOUT_S = 270                       # Quick her MCP çağrısında 300 sn bekler


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config

    return boto3.client("bedrock-agentcore", config=Config(read_timeout=READ_TIMEOUT_S, retries={"max_attempts": 1}))


def parse_stream(lines) -> str:
    """Supervisor akışından (`data: {...}`) metni toplar; mesajlar satırla ayrılır; `error` olayında RuntimeError."""
    messages: list[list[str]] = [[]]
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data: "):
            continue
        try:
            ev = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if ev.get("error"):
            raise RuntimeError(str(ev["error"]))
        event = ev.get("event") or {}
        if "messageStart" in event and messages[-1]:
            messages.append([])
        text = ((event.get("contentBlockDelta") or {}).get("delta") or {}).get("text")
        if text:
            messages[-1].append(text)
    return "\n".join("".join(m).strip() for m in messages if "".join(m).strip())


def _tool_name(context) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    return str(custom.get("bedrockAgentCoreToolName", "")).split("___")[-1]


def handler(event, context):
    tool = _tool_name(context)
    if tool != TOOL_NAME:
        return {"error": f"Bilinmeyen araç: {tool or '(yok)'}"}
    question = str((event or {}).get("question") or "").strip()
    if not question:
        return {"error": "Soru boş."}
    if len(question) > MAX_QUESTION:
        return {"error": f"Soru en çok {MAX_QUESTION} karakter olabilir."}
    day = (event or {}).get("day")
    payload = {"prompt": question, "actorId": os.environ.get("QUICK_ACTOR_ID", "MUDUR-QUICK"),
               **({"day": int(day)} if isinstance(day, (int, float)) and day else {})}
    body = None
    try:
        resp = _client().invoke_agent_runtime(
            agentRuntimeArn=os.environ["SUPERVISOR_RUNTIME_ARN"], runtimeSessionId=f"quick-{uuid.uuid4().hex}",
            payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            contentType="application/json", accept="text/event-stream")
        body = resp["response"]
        answer = parse_stream(body.iter_lines())
    except RuntimeError as e:
        log.warning("supervisor hata akıttı: %s", e)
        return {"error": f"Ajan yanıt veremedi: {e}"}
    except Exception as e:  # noqa: BLE001 - AWS ayrıntısı log'a; Quick'e kısa ve güvenli mesaj
        log.exception("supervisor çağrısı başarısız")
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        return {"error": f"Courier Memory ajanına şu an ulaşılamıyor ({code})."}
    finally:
        if body is not None:
            body.close()
    return {"answer": answer or "Ajan boş yanıt döndürdü."}
