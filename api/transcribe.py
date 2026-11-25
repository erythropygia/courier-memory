"""Sesli not → metin (P1: Amazon Transcribe Streaming, tr-TR). /api/speech (Polly) ile aynı desen:
CM_TRANSCRIBE=1 değilse 501 döner, arayüz tarayıcının ses tanımasına (Web Speech API) düşer.

Biçim: ham gövde. Arayüz MediaRecorder kaydını tarayıcıda 16 kHz mono PCM'e çevirip `audio/pcm;rate=16000`
gönderir (Chrome webm, Safari mp4 kaydeder; Transcribe Streaming yalnız PCM / FLAC / Ogg Opus kabul eder).
Ses kaydedilmez ve günlüğe yazılmaz; yanıtta AWS ayrıntısı (hesap, ARN, istisna metni) yer almaz.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from api import transcribe_client

log = logging.getLogger("cm.transcribe")

LANGUAGE = "tr-TR"
MAX_SECONDS = 60
MAX_BYTES = 2_000_000            # 60 sn · 16 kHz · 16 bit PCM ≈ 1,92 MB
MIN_PCM_SECONDS = 0.25
RATE_RANGE = (8_000, 48_000)
DEFAULT_TIMEOUT_S = 30.0
# MIME türü → (Transcribe kodlaması, varsayılan örnekleme hızı)
ENCODINGS = {
    "audio/pcm": ("pcm", 16_000), "audio/l16": ("pcm", 16_000), "audio/x-pcm": ("pcm", 16_000),
    "audio/ogg": ("ogg-opus", 48_000), "audio/opus": ("ogg-opus", 48_000),
    "audio/flac": ("flac", 16_000), "audio/x-flac": ("flac", 16_000),
}

MSG_DISABLED = "Sunucu ses tanıması (Amazon Transcribe) kapalı; tarayıcının ses tanıması kullanılır."
MSG_NO_SDK = "Sunucu ses tanıması kurulu değil; tarayıcının ses tanıması kullanılır."
MSG_TOO_LONG = f"Ses kaydı çok uzun; en fazla {MAX_SECONDS} saniye konuşun."
MSG_EMPTY = "Ses kaydı boş."
MSG_TOO_SHORT = "Ses kaydı çok kısa; düğmeyi basılı tutup konuşun."
MSG_RATE = f"Örnekleme hızı {RATE_RANGE[0]}–{RATE_RANGE[1]} Hz arasında olmalı."
MSG_PCM = "PCM ses 16 bit (2 bayt/örnek) olmalı."
MSG_TIMEOUT = "Ses çözümleme zaman aşımına uğradı; tekrar deneyin ya da notu yazın."
MSG_FAILED = "Ses çözümlenemedi; tekrar deneyin ya da notu yazın."


class TranscribeError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class AudioFormat:
    encoding: str
    sample_rate: int


def enabled() -> bool:
    return os.environ.get("CM_TRANSCRIBE", "0") == "1"


def sdk_installed() -> bool:
    return importlib.util.find_spec("amazon_transcribe") is not None


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def timeout_s() -> float:
    try:
        return max(1.0, float(os.environ.get("CM_TRANSCRIBE_TIMEOUT", DEFAULT_TIMEOUT_S)))
    except ValueError:
        return DEFAULT_TIMEOUT_S


def parse_format(content_type: str | None) -> AudioFormat:
    """`audio/pcm;rate=16000` → AudioFormat('pcm', 16000). Bilinmeyen tür 415, geçersiz hız 400."""
    mime, *params = [p.strip() for p in (content_type or "").split(";")]
    mime = mime.lower()
    if mime not in ENCODINGS:
        shown = mime[:60] or "yok"
        raise TranscribeError(415, f"Desteklenmeyen ses biçimi ({shown}). 16 kHz PCM (audio/pcm), "
                                   "Ogg Opus (audio/ogg) ya da FLAC (audio/flac) gönderin.")
    encoding, rate = ENCODINGS[mime]
    opts = dict(p.split("=", 1) for p in params if "=" in p)
    raw = (opts.get("rate") or "").strip()
    if raw:
        if not raw.isdigit():
            raise TranscribeError(400, MSG_RATE)
        rate = int(raw)
    if not RATE_RANGE[0] <= rate <= RATE_RANGE[1]:
        raise TranscribeError(400, MSG_RATE)
    return AudioFormat(encoding, rate)


def validate_audio(audio: bytes, fmt: AudioFormat) -> None:
    if not audio:
        raise TranscribeError(400, MSG_EMPTY)
    if len(audio) > MAX_BYTES:
        raise TranscribeError(413, MSG_TOO_LONG)
    if fmt.encoding != "pcm":
        return
    if len(audio) % 2:
        raise TranscribeError(400, MSG_PCM)
    seconds = len(audio) / (2 * fmt.sample_rate)
    if seconds > MAX_SECONDS:
        raise TranscribeError(413, MSG_TOO_LONG)
    if seconds < MIN_PCM_SECONDS:
        raise TranscribeError(400, MSG_TOO_SHORT)


async def read_body(request: Request, limit: int = MAX_BYTES) -> bytes:
    """Gövdeyi sınırı aşmadan okur (Content-Length'e güvenmeden)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise TranscribeError(413, MSG_TOO_LONG)
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > limit:
            raise TranscribeError(413, MSG_TOO_LONG)
    return bytes(buf)


def _check_available() -> None:
    if not enabled():
        raise TranscribeError(501, MSG_DISABLED)
    if not sdk_installed():
        raise TranscribeError(501, MSG_NO_SDK)


async def _transcribe(audio: bytes, fmt: AudioFormat) -> str:
    try:
        text = await asyncio.wait_for(
            transcribe_client.stream_transcribe(audio, encoding=fmt.encoding, sample_rate=fmt.sample_rate,
                                                language=LANGUAGE, region=region()),
            timeout=timeout_s())
    except asyncio.TimeoutError:
        log.warning("Transcribe zaman aşımı (%.0f sn, %d bayt)", timeout_s(), len(audio))
        raise TranscribeError(504, MSG_TIMEOUT) from None
    except transcribe_client.TranscribeUnavailable:
        raise TranscribeError(501, MSG_NO_SDK) from None
    except Exception as e:  # ayrıntı yalnız sunucu günlüğünde; yanıtta AWS bilgisi yok
        log.warning("Transcribe hatası: %s: %s", type(e).__name__, e)
        raise TranscribeError(502, MSG_FAILED) from None
    return " ".join((text or "").split())


def status() -> JSONResponse:
    """GET /api/transcribe: arayüz kayıttan önce sunucu tanımasının açık olup olmadığını sorar."""
    try:
        _check_available()
    except TranscribeError as e:
        return JSONResponse({"detail": e.detail, "enabled": False}, status_code=e.status)
    return JSONResponse({"enabled": True, "language": LANGUAGE, "max_seconds": MAX_SECONDS,
                         "formats": sorted(ENCODINGS)})


async def handle(request: Request) -> JSONResponse:
    """POST /api/transcribe: ham ses gövdesi → {"text", "language"}."""
    try:
        _check_available()
        fmt = parse_format(request.headers.get("content-type"))
        audio = await read_body(request)
        validate_audio(audio, fmt)
        text = await _transcribe(audio, fmt)
    except TranscribeError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
    return JSONResponse({"text": text, "language": LANGUAGE})
