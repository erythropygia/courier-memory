"""/api/speech: Polly çağrısı (ses + motor), kapalıyken ve hatada 501 (arayüz tarayıcı sesine düşer)."""
import io
import sys
import types

import pytest
from fastapi.testclient import TestClient

from api import main


class _FakePolly:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def synthesize_speech(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("ValidationException")
        return {"AudioStream": io.BytesIO(b"ID3mp3")}


@pytest.fixture
def setup(monkeypatch):
    def make(mode="live", fail=False, **env):
        for k in ("CM_POLLY_VOICE", "CM_POLLY_ENGINE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("CM_POLLY", "1")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        llm = types.SimpleNamespace(mode=mode, region="us-east-1")
        monkeypatch.setattr(main, "sv", lambda: types.SimpleNamespace(llm=llm))
        polly, regions = _FakePolly(fail), []
        fake = types.SimpleNamespace(client=lambda name, region_name=None: regions.append((name, region_name)) or polly)
        monkeypatch.setitem(sys.modules, "boto3", fake)
        return TestClient(main.app), polly, regions
    return make


def test_default_is_burcu_neural(setup):
    client, polly, regions = setup()
    r = client.get("/api/speech?text=merhaba")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3mp3"
    assert regions == [("polly", "us-east-1")]
    assert polly.calls == [{"Text": "merhaba", "OutputFormat": "mp3", "VoiceId": "Burcu", "Engine": "neural", "LanguageCode": "tr-TR"}]


def test_filiz_uses_standard_engine(setup):
    client, polly, _ = setup(CM_POLLY_VOICE="Filiz")
    assert client.get("/api/speech?text=merhaba").status_code == 200
    assert polly.calls[0]["VoiceId"] == "Filiz" and polly.calls[0]["Engine"] == "standard"


def test_empty_voice_env_falls_back_to_default(setup):
    client, polly, _ = setup(CM_POLLY_VOICE="", CM_POLLY_ENGINE="")
    assert client.get("/api/speech?text=merhaba").status_code == 200
    assert polly.calls[0]["VoiceId"] == "Burcu" and polly.calls[0]["Engine"] == "neural"


def test_disabled_mock_and_error_return_501(setup, monkeypatch):
    client, polly, _ = setup(fail=True)
    r = client.get("/api/speech?text=merhaba")
    assert r.status_code == 501 and "Polly hatası" in r.json()["detail"]
    client, polly, _ = setup(mode="mock")
    assert client.get("/api/speech?text=merhaba").status_code == 501 and polly.calls == []
    client, polly, _ = setup()
    monkeypatch.setenv("CM_POLLY", "0")
    assert client.get("/api/speech?text=merhaba").status_code == 501 and polly.calls == []


def test_text_length_bounds(setup):
    client, polly, _ = setup()
    assert client.get("/api/speech?text=" + "a" * 601).status_code == 422
    assert client.get("/api/speech?text=").status_code == 422
    assert polly.calls == []
