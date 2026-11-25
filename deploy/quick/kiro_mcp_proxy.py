"""Kiro → Courier Memory canlı ajanları (stdio MCP aracısı).

Kiro bu süreci `.kiro/settings/mcp.json` ile başlatır. Aracı, Amazon Quick için kurulan köprüyü (AgentCore Gateway, MCP)
kullanır: Cognito'dan istemci kimliğiyle jeton alır, süresi dolmadan yeniler ve `ask_courier_memory` çağrısını Gateway'e
iletir. Cevabı dağıtılmış Supervisor ve uzman ajanlar verir (müdür kimliği MUDUR-QUICK; ayrıntı: deploy/quick/README.md).

Ayarlar repo kökündeki `.env` dosyasından okunur (git'e girmez); ortamda tanımlı olan değer önceliklidir:
  QUICK_MCP_URL  QUICK_CLIENT_ID  QUICK_CLIENT_SECRET  QUICK_TOKEN_URL  QUICK_SCOPE

  uv run --no-project --with mcp python deploy/quick/kiro_mcp_proxy.py
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ("QUICK_MCP_URL", "QUICK_CLIENT_ID", "QUICK_CLIENT_SECRET", "QUICK_TOKEN_URL")
GATEWAY_TOOL = "courier-memory___ask_courier_memory"
TIMEOUT_S = 290                          # Gateway/Quick üst sınırı 300 sn
REFRESH_MARGIN_S = 60


class ProxyError(RuntimeError):
    """Kullanıcıya gösterilebilir hata (gizli değer içermez)."""


def load_env(path: Path = ROOT / ".env", environ: dict | None = None) -> dict:
    """`.env` (KEY=VALUE) değerlerini döndürür; `environ`'da tanımlı olanlar kazanır."""
    environ = dict(os.environ if environ is None else environ)
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key.replace("_", "").isalnum():
                values[key] = val
    return {**values, **{k: v for k, v in environ.items() if v}}


@dataclass(frozen=True)
class Settings:
    mcp_url: str
    client_id: str
    client_secret: str = field(repr=False)
    token_url: str
    scope: str

    @classmethod
    def from_env(cls, env: dict) -> "Settings":
        missing = [k for k in REQUIRED if not env.get(k)]
        if missing:
            raise ProxyError(f".env içinde eksik: {', '.join(missing)} (değerler: deploy/quick/quick_bridge_setup.py çıktısı)")
        return cls(env["QUICK_MCP_URL"], env["QUICK_CLIENT_ID"], env["QUICK_CLIENT_SECRET"], env["QUICK_TOKEN_URL"],
                   env.get("QUICK_SCOPE") or "courier-memory/invoke")


def _http_json(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - yalnız .env'deki https uç noktaları
        return json.loads(r.read().decode("utf-8"))


class BridgeClient:
    def __init__(self, settings: Settings, http=_http_json, now=time.monotonic):
        self.s, self.http, self.now = settings, http, now
        self._token, self._expires, self._lock, self._id = None, 0.0, threading.Lock(), 0

    def _bearer(self) -> str:
        with self._lock:
            if self._token and self.now() < self._expires - REFRESH_MARGIN_S:
                return self._token
            basic = base64.b64encode(f"{self.s.client_id}:{self.s.client_secret}".encode()).decode()
            body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": self.s.scope}).encode()
            tok = self.http(self.s.token_url, body, {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {basic}"})
            self._token, self._expires = tok["access_token"], self.now() + float(tok.get("expires_in", 3600))
            return self._token

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, **({"params": params} if params else {})}).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": f"Bearer {self._bearer()}"}
        res = self.http(self.s.mcp_url, body, headers)
        if "error" in res:
            raise ProxyError(f"Köprü hatası: {res['error'].get('message', res['error'])}")
        return res["result"]

    def ask(self, question: str, day: int | None = None) -> str:
        if not self._id:
            self._rpc("tools/list")                                          # bağlantı ve yetki denetimi
        args = {"question": question, **({"day": day} if day else {})}
        result = self._rpc("tools/call", {"name": GATEWAY_TOOL, "arguments": args})
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise ProxyError(text or "Köprü aracı hata döndürdü.")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if payload.get("error"):
            raise ProxyError(str(payload["error"]))
        return payload.get("answer") or text


def build_server():
    try:                                    # mcp 2.x
        from mcp.server.mcpserver import MCPServer as _Server
    except ImportError:                     # mcp 1.x
        from mcp.server.fastmcp import FastMCP as _Server

    server = _Server("courier-memory-live")
    client: list[BridgeClient] = []

    @server.tool()
    def ask_courier_memory(question: str, day: int | None = None) -> str:
        """Dağıtılmış Courier Memory ajanlarına (Supervisor + Planlama, Kurye, Hafıza, Analiz) canlı soru sorar, müdür
        yetkisiyle. Günün planı, kurye brifingi, adres hafızası, hasat soruları, 40 günlük geçmiş veriden SQL analiz.
        Cevap 10-60 sn sürebilir.

        Args:
            question: Soru, eksiksiz ve tek parça (Türkçe olabilir).
            day: İsteğe bağlı simülasyon günü (20-39).
        """
        if not client:
            client.append(BridgeClient(Settings.from_env(load_env())))
        try:
            return client[0].ask(question, day)
        except ProxyError as e:
            return f"Hata: {e}"
        except Exception as e:  # noqa: BLE001 - ağ hatası; ayrıntı (jeton, gizli değer) gösterilmez
            return f"Hata: köprüye ulaşılamadı ({type(e).__name__})."

    return server


if __name__ == "__main__":
    build_server().run()
