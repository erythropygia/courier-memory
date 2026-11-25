"""Amazon Transcribe Streaming bağdaştırıcısı: SDK'ya dokunan tek dosya (testlerde bu modül taklit edilir).

Boto3 Transcribe Streaming'i desteklemez; AWS'nin async Python SDK'sı (amazon-transcribe, awscrt) kullanılır.
Ses diske ya da S3'e yazılmaz; parçalar halinde akışa verilir, yalnız kesinleşmiş (partial olmayan) sonuçlar birleştirilir.
"""
from __future__ import annotations

import asyncio

CHUNK_BYTES = 3_200  # 16 kHz · 16 bit · mono için 100 ms; SDK sınırı 32 KB


class TranscribeUnavailable(RuntimeError):
    """SDK kurulu değil: uç nokta 501 döner, arayüz tarayıcı tanımasına düşer."""


def _chunks(audio: bytes, size: int = CHUNK_BYTES):
    for i in range(0, len(audio), size):
        yield audio[i:i + size]


async def stream_transcribe(audio: bytes, *, encoding: str, sample_rate: int, language: str, region: str) -> str:
    """Sesi Transcribe Streaming'e gönderir, kesinleşmiş metni döner. Hatalar SDK istisnası olarak yükselir."""
    try:
        from amazon_transcribe.client import TranscribeStreamingClient
        from amazon_transcribe.model import TranscriptEvent
    except ImportError as e:  # pragma: no cover - kurulumda paket var; yoksa arayüz yedeğe düşer
        raise TranscribeUnavailable("amazon-transcribe paketi kurulu değil") from e

    client = TranscribeStreamingClient(region=region)
    stream = await client.start_stream_transcription(language_code=language, media_sample_rate_hz=sample_rate,
                                                     media_encoding=encoding)

    async def send() -> None:
        for chunk in _chunks(audio):
            await stream.input_stream.send_audio_event(audio_chunk=chunk)
        await stream.input_stream.end_stream()

    async def receive() -> list[str]:
        parts: list[str] = []
        async for event in stream.output_stream:
            if not isinstance(event, TranscriptEvent):
                continue
            for result in event.transcript.results or []:
                if result.is_partial or not result.alternatives:
                    continue
                text = (result.alternatives[0].transcript or "").strip()
                if text:
                    parts.append(text)
        return parts

    _, parts = await asyncio.gather(send(), receive())
    return " ".join(parts)
