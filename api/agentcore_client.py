"""Web → AgentCore Supervisor çağrısı (`bedrock-agentcore` InvokeAgentRuntime), akışı satır satır JSON olarak verir.

Supervisor runtime'ı adla bulunur (`bedrock-agentcore-control` ListAgentRuntimes; ad `CM_AGENTCORE_SUPERVISOR`,
varsayılan `CourierMemory_default_agent`) ve ARN önbelleğe alınır. Yeniden deneme yok (zincirde `leave_note` yazma
işlemidir, tekrar not bırakmasın); okuma zaman aşımı 120 sn. Hatalar `AgentCoreError`'a çevrilir: mesaj Türkçe ve
gösterilebilir, ARN / hesap numarası / ham istisna metni içermez (ayrıntı yalnız sunucu günlüğüne yazılır).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Iterator

log = logging.getLogger("cm.agentcore")

NAME_ENV = "CM_AGENTCORE_SUPERVISOR"
DEFAULT_NAME = "CourierMemory_default_agent"
REGION_ENV = "CM_AGENTCORE_REGION"
DEFAULT_REGION = "us-east-1"
MIN_SESSION_LEN = 33                     # AgentCore runtimeSessionId alt sınırı
READ_TIMEOUT_S = 120
CONNECT_TIMEOUT_S = 10

MSG_NO_CREDS = "Sunucuda AWS kimliği yok; AgentCore zinciri bu ortamda çalışamaz."
MSG_NO_SDK = "Sunucuda AWS SDK'sı (boto3) kurulu değil; AgentCore zinciri çalışamaz."
MSG_DENIED = "AgentCore'a erişim izni yok. Web görev rolünde InvokeAgentRuntime ve ListAgentRuntimes izni olmalı."
MSG_MISSING = "AgentCore Supervisor runtime'ı bulunamadı; AgentCore dağıtımını (agentcore deploy) kontrol edin."
MSG_AMBIGUOUS = "Aynı adla birden fazla Supervisor runtime'ı var; CM_AGENTCORE_SUPERVISOR ile birini seçin."
MSG_CONNECT = "AgentCore'a bağlanılamadı; ağ ya da bölge ayarını kontrol edin."
MSG_TIMEOUT = f"AgentCore {READ_TIMEOUT_S} sn içinde yanıt vermedi; adım zaman aşımına uğradı."
MSG_THROTTLED = "AgentCore şu an yoğun (istek sınırı); biraz sonra tekrar deneyin."
MSG_INVALID = "AgentCore isteği geçersiz buldu; istek gövdesini kontrol edin."
MSG_RUNTIME = "AgentCore Supervisor şu an yanıt veremiyor; biraz sonra tekrar deneyin."

_FATAL_CODES = {"AccessDeniedException", "AccessDenied", "UnrecognizedClientException", "InvalidSignatureException",
                "ExpiredTokenException", "ExpiredToken", "InvalidClientTokenId", "UnauthorizedException"}
_ARN = re.compile(r"arn:aws[\w-]*:[^\s\"'`,;)]+")
_ACCOUNT = re.compile(r"(?<!\d)\d{12}(?!\d)")


class AgentCoreError(RuntimeError):
    """Gösterilebilir hata. `fatal`: sonraki adımlar da aynı nedenle düşer (kimlik, izin, runtime yok); zincir durur."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


def supervisor_name() -> str:
    return (os.environ.get(NAME_ENV) or DEFAULT_NAME).strip()


def region() -> str:
    return os.environ.get(REGION_ENV) or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION


def scrub(text: object, limit: int = 400) -> str:
    """Dışarıdan gelen metinden ARN ve 12 haneli hesap numarasını çıkarır, kısaltır."""
    s = _ACCOUNT.sub("<hesap>", _ARN.sub("<arn>", str(text or "")))
    return s if len(s) <= limit else s[:limit] + "…"


def session_id(tag: str) -> str:
    """Koşu + kimlik başına bir oturum (konuşma geçmişi karışmaz); AgentCore deseni: harf, rakam, -, _."""
    safe = re.sub(r"[^A-Za-z0-9-]", "-", tag).strip("-").lower() or "x"
    sid = f"cm-live-{safe}-{uuid.uuid4().hex}"
    return sid if len(sid) >= MIN_SESSION_LEN else sid.ljust(MIN_SESSION_LEN, "0")


def make_client(service: str):
    import boto3
    from botocore.config import Config

    return boto3.client(service, region_name=region(),
                        config=Config(read_timeout=READ_TIMEOUT_S, connect_timeout=CONNECT_TIMEOUT_S,
                                      retries={"total_max_attempts": 1, "mode": "standard"}))


def parse_line(raw: bytes | str) -> dict | None:
    """`data: {...}` satırı → sözlük; boş, yorum ya da bozuk satır → None."""
    line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    line = line.strip()
    if not line.startswith("data:"):
        return None
    try:
        ev = json.loads(line[5:].strip())
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


def friendly(e: BaseException) -> AgentCoreError:
    """İstisna → gösterilebilir hata. Ham metin (ARN, hesap) dışarı çıkmaz."""
    if isinstance(e, AgentCoreError):
        return e
    if isinstance(e, ImportError):
        return AgentCoreError(MSG_NO_SDK, fatal=True)
    try:
        from botocore import exceptions as bx
    except ImportError:
        return AgentCoreError(MSG_NO_SDK, fatal=True)
    if isinstance(e, (bx.NoCredentialsError, bx.PartialCredentialsError, bx.NoRegionError)):
        return AgentCoreError(MSG_NO_CREDS, fatal=True)
    if isinstance(e, (bx.ReadTimeoutError, bx.ConnectTimeoutError)):
        return AgentCoreError(MSG_TIMEOUT)
    if isinstance(e, bx.EndpointConnectionError):
        return AgentCoreError(MSG_CONNECT, fatal=True)
    if isinstance(e, bx.ClientError):
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code in _FATAL_CODES:
            return AgentCoreError(MSG_DENIED, fatal=True)
        if code == "ResourceNotFoundException":
            return AgentCoreError(MSG_MISSING, fatal=True)
        if code in ("ThrottlingException", "ServiceQuotaExceededException", "TooManyRequestsException"):
            return AgentCoreError(MSG_THROTTLED)
        if code == "ValidationException":
            return AgentCoreError(MSG_INVALID)
        return AgentCoreError(f"{MSG_RUNTIME} ({re.sub(r'[^A-Za-z]', '', code)[:40] or 'hata'})")
    return AgentCoreError(f"{MSG_RUNTIME} ({type(e).__name__})")


class SupervisorClient:
    """Supervisor'ı çağırır. `factory(service)` boto3 istemcisi döndürür (testler sahtesini verir)."""

    def __init__(self, factory=None):
        self._factory = factory
        self._clients: dict[str, object] = {}
        self._arn: str | None = None
        self._lock = threading.Lock()

    def _client(self, service: str):
        with self._lock:
            if service not in self._clients:
                self._clients[service] = (self._factory or make_client)(service)
            return self._clients[service]

    def forget(self) -> None:
        with self._lock:
            self._arn = None

    def arn(self) -> str:
        with self._lock:
            if self._arn:
                return self._arn
        name = supervisor_name()
        ctl = self._client("bedrock-agentcore-control")
        found, token = [], None
        while True:                                   # ağ çağrısı kilit dışında
            resp = ctl.list_agent_runtimes(**({"nextToken": token} if token else {}))
            found += [r.get("agentRuntimeArn") for r in resp.get("agentRuntimes", []) if r.get("agentRuntimeName") == name]
            token = resp.get("nextToken")
            if not token:
                break
        if not found:
            raise AgentCoreError(MSG_MISSING, fatal=True)
        if len(found) > 1:
            raise AgentCoreError(MSG_AMBIGUOUS, fatal=True)
        with self._lock:
            self._arn = found[0]
            return self._arn

    def invoke(self, payload: dict, session: str) -> Iterator[dict]:
        """Supervisor akışının JSON satırları (`{"event"}`, `{"cm_trace"}`, `{"error"}`), geldikçe."""
        body = None
        try:
            resp = self._client("bedrock-agentcore").invoke_agent_runtime(
                agentRuntimeArn=self.arn(), runtimeSessionId=session,
                payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                contentType="application/json", accept="text/event-stream")
            body = resp["response"]
            if str(resp.get("contentType", "")).startswith("application/json"):     # akışsız yanıt: tek JSON
                one = json.loads(body.read() or b"{}")
                yield one if isinstance(one, dict) else {"error": "Beklenmeyen yanıt biçimi"}
                return
            for raw in body.iter_lines():
                ev = parse_line(raw)
                if ev is not None:
                    yield ev
        except Exception as e:  # noqa: BLE001 - her hata gösterilebilir mesaja çevrilir, ayrıntı günlükte
            err = friendly(e)
            if err.fatal:
                self.forget()                         # runtime yeniden kurulduysa sonraki koşu ARN'yi yeniden bulur
            log.warning("AgentCore çağrısı başarısız: actor=%s %s", payload.get("actorId"), type(e).__name__, exc_info=True)
            raise err from None
        finally:
            if body is not None and hasattr(body, "close"):
                try:
                    body.close()
                except Exception:  # noqa: BLE001
                    pass


_DEFAULT: SupervisorClient | None = None
_DEFAULT_LOCK = threading.Lock()


def default_client() -> SupervisorClient:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = SupervisorClient()
        return _DEFAULT
