"""POST/GET /api/transcribe: Transcribe istemcisi taklit edilir; AWS'ye çağrı yok."""
import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from api import main, transcribe, transcribe_client

PCM = "audio/pcm;rate=16000"
ONE_SECOND = b"\x01\x00" * 16_000


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CM_TRANSCRIBE", "1")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.delenv("CM_TRANSCRIBE_TIMEOUT", raising=False)
    return TestClient(main.app)


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    async def fake(audio, *, encoding, sample_rate, language, region):
        seen.append({"bytes": len(audio), "encoding": encoding, "sample_rate": sample_rate,
                     "language": language, "region": region})
        return "  asansör yok,   4. kata merdivenle çıkılıyor "

    monkeypatch.setattr(transcribe_client, "stream_transcribe", fake)
    return seen


def _post(client, body=ONE_SECOND, content_type=PCM):
    return client.post("/api/transcribe", content=body, headers={"Content-Type": content_type})


def test_disabled_returns_501_for_status_and_upload(client, calls, monkeypatch):
    monkeypatch.setenv("CM_TRANSCRIBE", "0")
    for r in (client.get("/api/transcribe"), _post(client)):
        assert r.status_code == 501
        assert "tarayıcı" in r.json()["detail"]
    assert calls == []


def test_status_enabled(client):
    r = client.get("/api/transcribe")
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["language"] == "tr-TR"


def test_pcm_transcribed_to_turkish_text(client, calls):
    r = _post(client)
    assert r.status_code == 200
    assert r.json() == {"text": "asansör yok, 4. kata merdivenle çıkılıyor", "language": "tr-TR"}
    assert calls == [{"bytes": 32_000, "encoding": "pcm", "sample_rate": 16_000, "language": "tr-TR",
                      "region": "eu-central-1"}]


def test_ogg_opus_defaults_to_48k(client, calls):
    assert _post(client, b"OggS" + b"\x00" * 500, "audio/ogg;codecs=opus").status_code == 200
    assert calls[0]["encoding"] == "ogg-opus" and calls[0]["sample_rate"] == 48_000


@pytest.mark.parametrize("content_type", ["audio/webm;codecs=opus", "application/json", "text/plain", ""])
def test_unsupported_content_type_is_415(client, calls, content_type):
    r = _post(client, content_type=content_type)
    assert r.status_code == 415 and "Desteklenmeyen" in r.json()["detail"]
    assert calls == []


def test_too_large_is_413(client, calls):
    r = _post(client, b"\x00" * (transcribe.MAX_BYTES + 2))
    assert r.status_code == 413 and "60 saniye" in r.json()["detail"]
    over_60s_at_8k = b"\x00\x00" * 8_000 * 61
    assert _post(client, over_60s_at_8k, "audio/pcm;rate=8000").status_code == 413
    assert calls == []


@pytest.mark.parametrize("body,content_type", [
    (b"", PCM),                              # boş
    (b"\x00\x00" * 100, PCM),                # çok kısa
    (b"\x00" * 32_001, PCM),                 # tek sayıda bayt: 16 bit değil
    (ONE_SECOND, "audio/pcm;rate=96000"),    # hız aralık dışı
    (ONE_SECOND, "audio/pcm;rate=abc"),
])
def test_bad_audio_is_400(client, calls, body, content_type):
    assert _post(client, body, content_type).status_code == 400
    assert calls == []


def test_service_error_is_friendly_502_without_aws_details(client, monkeypatch, caplog):
    async def boom(*a, **k):
        raise RuntimeError("AccessDenied arn:aws:iam::123456789012:role/web")

    monkeypatch.setattr(transcribe_client, "stream_transcribe", boom)
    with caplog.at_level(logging.WARNING, logger="cm.transcribe"):
        r = _post(client)
    assert r.status_code == 502
    assert r.json()["detail"] == transcribe.MSG_FAILED
    assert "arn:" not in r.text and "123456789012" not in r.text
    assert "RuntimeError" in caplog.text  # ayrıntı yalnız sunucu günlüğünde


def test_timeout_is_504(client, monkeypatch):
    async def slow(*a, **k):
        await asyncio.sleep(5)
        return "geç"

    monkeypatch.setattr(transcribe_client, "stream_transcribe", slow)
    monkeypatch.setattr(transcribe, "timeout_s", lambda: 0.05)
    r = _post(client)
    assert r.status_code == 504 and "zaman aşımı" in r.json()["detail"]


def test_missing_sdk_is_501(client, calls, monkeypatch):
    monkeypatch.setattr(transcribe, "sdk_installed", lambda: False)
    assert _post(client).status_code == 501
    assert client.get("/api/transcribe").status_code == 501


def test_chunks_respect_sdk_limit():
    chunks = list(transcribe_client._chunks(b"\x00" * 10_000))
    assert sum(map(len, chunks)) == 10_000 and max(map(len, chunks)) <= 32 * 1024


def test_adapter_sends_chunks_and_keeps_only_final_results(monkeypatch):
    """SDK sahte modüllerle değiştirilir: kısmi sonuçlar atılır, kesinleşenler birleştirilir."""
    import sys
    import types
    from types import SimpleNamespace as NS

    class TranscriptEvent:
        def __init__(self, results):
            self.transcript = NS(results=results)

    sent, started = [], {}

    class Input:
        async def send_audio_event(self, audio_chunk):
            sent.append(audio_chunk)

        async def end_stream(self):
            sent.append(None)

    async def output():
        yield TranscriptEvent([NS(is_partial=True, alternatives=[NS(transcript="asan")])])
        yield TranscriptEvent([NS(is_partial=False, alternatives=[NS(transcript="asansör yok")])])
        yield object()  # başka olay türleri yok sayılır
        yield TranscriptEvent([NS(is_partial=False, alternatives=[NS(transcript="merdiven var")])])

    class Client:
        def __init__(self, region):
            started["region"] = region

        async def start_stream_transcription(self, **kw):
            started.update(kw)
            return NS(input_stream=Input(), output_stream=output())

    monkeypatch.setitem(sys.modules, "amazon_transcribe", types.ModuleType("amazon_transcribe"))
    monkeypatch.setitem(sys.modules, "amazon_transcribe.client", NS(TranscribeStreamingClient=Client))
    monkeypatch.setitem(sys.modules, "amazon_transcribe.model", NS(TranscriptEvent=TranscriptEvent))
    text = asyncio.run(transcribe_client.stream_transcribe(b"\x00" * 7_000, encoding="pcm", sample_rate=16_000,
                                                           language="tr-TR", region="eu-central-1"))
    assert text == "asansör yok merdiven var"
    assert started == {"region": "eu-central-1", "language_code": "tr-TR", "media_sample_rate_hz": 16_000,
                       "media_encoding": "pcm"}
    assert [len(c) for c in sent[:-1]] == [3_200, 3_200, 600] and sent[-1] is None
