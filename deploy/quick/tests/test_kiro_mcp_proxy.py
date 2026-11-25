"""Kiro → Quick köprüsü MCP aracısı: .env okuma, jeton önbelleği, Gateway çağrısı. Ağa çıkmaz."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kiro_mcp_proxy as px  # noqa: E402

ENV = {"QUICK_MCP_URL": "https://gw.example/mcp", "QUICK_CLIENT_ID": "cid", "QUICK_CLIENT_SECRET": "s3cr3t",
       "QUICK_TOKEN_URL": "https://auth.example/oauth2/token", "QUICK_SCOPE": "courier-memory/invoke"}


def test_load_env_reads_values_without_overriding(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# yorum\nQUICK_CLIENT_ID=abc\nQUICK_SCOPE="courier-memory/invoke"\nEMPTY=\nBAD LINE\nAWS_REGION=eu\n', encoding="utf-8")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    env = px.load_env(f, environ={"AWS_REGION": "us-east-1"})
    assert env["QUICK_CLIENT_ID"] == "abc" and env["QUICK_SCOPE"] == "courier-memory/invoke"
    assert env["AWS_REGION"] == "us-east-1" and "BAD LINE" not in env


def test_missing_settings_are_named_but_secret_is_not_printed():
    with pytest.raises(px.ProxyError) as e:
        px.Settings.from_env({**ENV, "QUICK_CLIENT_SECRET": "", "QUICK_MCP_URL": ""})
    assert "QUICK_CLIENT_SECRET" in str(e.value) and "QUICK_MCP_URL" in str(e.value)
    assert "s3cr3t" not in repr(px.Settings.from_env(ENV))


class FakeHttp:
    def __init__(self, answer="Plan hazir.", expires_in=3600):
        self.calls, self.answer, self.expires_in = [], answer, expires_in

    def __call__(self, url, data, headers):
        self.calls.append({"url": url, "data": data, "headers": headers})
        if url.endswith("/token"):
            return {"access_token": f"tok{len(self.calls)}", "expires_in": self.expires_in}
        body = json.loads(data)
        if body["method"] == "tools/list":
            return {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "courier-memory___ask_courier_memory"}]}}
        text = json.dumps({"answer": self.answer}, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": body["id"], "result": {"isError": False, "content": [{"type": "text", "text": text}]}}


def test_ask_forwards_question_and_reuses_token():
    http, clock = FakeHttp(), [1000.0]
    client = px.BridgeClient(px.Settings.from_env(ENV), http=http, now=lambda: clock[0])
    assert client.ask("Bugünün planı?", day=32) == "Plan hazir."
    assert client.ask("Bir daha?") == "Plan hazir."
    token_calls = [c for c in http.calls if c["url"].endswith("/token")]
    assert len(token_calls) == 1                                           # jeton önbellekte
    assert token_calls[0]["headers"]["Authorization"].startswith("Basic ")
    call = json.loads([c for c in http.calls if c["url"] == ENV["QUICK_MCP_URL"]][-1]["data"])
    assert call["method"] == "tools/call" and call["params"]["name"] == "courier-memory___ask_courier_memory"
    first = json.loads([c for c in http.calls if c["url"] == ENV["QUICK_MCP_URL"]][1]["data"])
    assert first["params"]["arguments"] == {"question": "Bugünün planı?", "day": 32}


def test_token_is_refreshed_before_expiry():
    http, clock = FakeHttp(expires_in=600), [1000.0]
    client = px.BridgeClient(px.Settings.from_env(ENV), http=http, now=lambda: clock[0])
    client.ask("a")
    clock[0] += 590                                                          # süre dolmadan 60 sn önce yenilenir
    client.ask("b")
    assert len([c for c in http.calls if c["url"].endswith("/token")]) == 2


def test_bridge_error_is_returned_as_text():
    class ErrHttp(FakeHttp):
        def __call__(self, url, data, headers):
            r = super().__call__(url, data, headers)
            if not url.endswith("/token") and json.loads(data)["method"] == "tools/call":
                return {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": [{"type": "text", "text": "boom"}]}}
            return r

    client = px.BridgeClient(px.Settings.from_env(ENV), http=ErrHttp(), now=lambda: 0.0)
    with pytest.raises(px.ProxyError, match="boom"):
        client.ask("x")
