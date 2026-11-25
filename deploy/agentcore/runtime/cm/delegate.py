"""Supervisor → uzman ajan çağrısı: başka bir AgentCore runtime'ını `InvokeAgentRuntime` ile çağırır.

Uzman runtime'lar aynı projede `<Proje>_<hedef>_<rol>` adıyla dağıtılır (ör. CourierMemory_default_planner).
Supervisor ARN'yi adla bulur (`ListAgentRuntimes`); tek dağıtım yeter, ARN'yi önceden bilmek gerekmez.
`CM_RUNTIME_PREFIX` (bootstrap.sh yazar: "<Proje>_<hedef>_") zorunludur; `CM_<ROL>_RUNTIME_ARN` verilirse arama yapılmaz.

Kimlik modelden gelmez: uzmana isteğin `actorId`'si gider, uzman kendi kimlik sınırını (cm/scope.py) uygular.
İzinler: supervisor'ın rolüne agentcore_config.py `InvokeAgentRuntime` (yalnız bu proje + hedef) ve `ListAgentRuntimes` ekler.
Yeniden deneme yok: `leave_note` yazma işlemidir, tekrar not bırakmasın.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterable
from functools import lru_cache

log = logging.getLogger(__name__)

PREFIX_ENV = "CM_RUNTIME_PREFIX"
MIN_SESSION_LEN = 33                      # AgentCore runtimeSessionId alt sınırı
READ_TIMEOUT_S = 120

_arns: dict[str, str] = {}
_lock = threading.Lock()


class DelegationError(RuntimeError):
    """Uzman ajana ulaşılamadı ya da uzman hata döndürdü; mesaj kullanıcıya gösterilebilir (AWS ayrıntısı içermez)."""


def _region() -> str | None:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")


def specialist_session(session_id: str, role: str) -> str:
    """Her uzmanın kendi oturumu olur (konuşma geçmişi karışmaz); kimlik aynı oturumda sabit kalır."""
    sid = f"{session_id}-{role}"
    return sid if len(sid) >= MIN_SESSION_LEN else sid.ljust(MIN_SESSION_LEN, "0")


def resolve_arn(role: str, listing: Iterable[dict] | None = None) -> str:
    override = os.environ.get(f"CM_{role.upper()}_RUNTIME_ARN")
    if override:
        return override
    prefix = os.environ.get(PREFIX_ENV, "")
    if not prefix:
        raise DelegationError(f"{PREFIX_ENV} tanımlı değil; uzman runtime'ı güvenle seçilemez (bootstrap.sh yazar).")
    items = list(listing) if listing is not None else _list_runtimes()
    wanted = f"{prefix}{role}"
    found = [r["agentRuntimeArn"] for r in items if r.get("agentRuntimeName") == wanted]
    if not found:
        raise DelegationError(f"{role} uzman runtime'ı bulunamadı ({wanted}); bootstrap.sh + agentcore deploy ile dağıtıldığını kontrol edin.")
    if len(found) > 1:
        raise DelegationError(f"{wanted} adında birden fazla runtime var; CM_{role.upper()}_RUNTIME_ARN ile birini seçin.")
    return found[0]


def _list_runtimes() -> list[dict]:
    import boto3

    client = boto3.client("bedrock-agentcore-control", region_name=_region())
    out, token = [], None
    while True:
        resp = client.list_agent_runtimes(**({"nextToken": token} if token else {}))
        out.extend(resp.get("agentRuntimes", []))
        token = resp.get("nextToken")
        if not token:
            return out


def _arn(role: str) -> str:
    with _lock:
        cached = _arns.get(role)
    if cached:
        return cached
    arn = resolve_arn(role)                # ağ çağrısı kilit dışında: eşzamanlı ilk istekler birbirini beklemez
    with _lock:
        return _arns.setdefault(role, arn)


def _forget(role: str) -> None:
    with _lock:
        _arns.pop(role, None)


@lru_cache(maxsize=1)
def _runtime_client():
    import boto3
    from botocore.config import Config

    return boto3.client("bedrock-agentcore", region_name=_region(),
                        config=Config(read_timeout=READ_TIMEOUT_S, retries={"max_attempts": 1, "mode": "standard"}))


def parse_stream(lines: Iterable[bytes | str]) -> str:
    """Uzmanın akışından (`data: {...}` satırları) metni toplar; mesajlar satırla ayrılır; `error` olayında DelegationError."""
    messages: list[list[str]] = [[]]
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data: "):
            continue
        try:
            ev = json.loads(line[len("data: "):])
        except json.JSONDecodeError:
            continue
        if ev.get("error"):
            raise DelegationError(str(ev["error"]))
        event = ev.get("event") or {}
        if "messageStart" in event and messages[-1]:
            messages.append([])
        delta = (event.get("contentBlockDelta") or {}).get("delta") or {}
        if delta.get("text"):
            messages[-1].append(delta["text"])
    return "\n".join("".join(m).strip() for m in messages if "".join(m).strip())


def invoke_specialist(role: str, prompt: str, actor_id: str, session_id: str, day: int | None = None) -> str:
    from botocore.exceptions import BotoCoreError, ClientError

    payload = {"prompt": prompt, "actorId": actor_id, **({"day": day} if day else {})}
    body = None
    try:
        resp = _runtime_client().invoke_agent_runtime(
            agentRuntimeArn=_arn(role), runtimeSessionId=specialist_session(session_id, role),
            payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            contentType="application/json", accept="text/event-stream")
        body = resp["response"]
        text = parse_stream(body.iter_lines())
    except (ClientError, BotoCoreError, KeyError) as e:
        _forget(role)                      # runtime silinip yeniden kurulduysa sonraki çağrı ARN'yi yeniden bulur
        log.exception("uzman çağrısı başarısız: role=%s actor=%s", role, actor_id)
        code = e.response.get("Error", {}).get("Code", "") if isinstance(e, ClientError) else type(e).__name__
        raise DelegationError(f"{role} uzmanına şu an ulaşılamıyor ({code}). Biraz sonra tekrar deneyin.") from e
    finally:
        if body is not None:
            body.close()
    if not text:
        raise DelegationError(f"{role} uzmanı boş yanıt döndürdü.")
    return text
