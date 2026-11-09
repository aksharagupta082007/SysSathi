"""Prisma speech-to-text client for REST and WebSocket streaming (V1, V2, V4)."""

from __future__ import annotations

import io
import json
import logging
import wave
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from syssathi.host.config import GNANI_API_KEY, KEYTERMS_LIST, PRISMA_MODE
from syssathi.voice.errors import SpeechError

logger = logging.getLogger(__name__)

PRISMA_REST_URL = "https://api.vachana.ai/stt/v3"
PRISMA_WS_URL = "wss://api.vachana.ai/stt/v3/stream"


class PrismaClient:
    """Client for Gnani Prisma v3.0 STT."""

    def __init__(
        self,
        api_key: str | None = None,
        mode: str | None = None,
        keyterms: list[str] | None = None,
    ) -> None:
        self.api_key = api_key or GNANI_API_KEY
        self.mode = mode or PRISMA_MODE or "Code-mix"
        self.keyterms = keyterms or KEYTERMS_LIST

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "recording.wav",
        language_code: str = "indic-auto",
    ) -> str:
        """Transcribe in-memory audio bytes via REST endpoint."""
        if not self.api_key:
            raise SpeechError("Prisma", "GNANI_API_KEY is not configured")

        headers = {"X-API-Key-ID": self.api_key}
        format_val = self.mode.lower().replace("-", "").replace("_", "")
        data = {
            "model": "prisma-v3.0",
            "language_code": language_code,
            "format": format_val,
            "keyterms": ", ".join(self.keyterms),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"audio_file": (filename, audio_bytes, "audio/wav")}
                resp = await client.post(PRISMA_REST_URL, data=data, files=files, headers=headers)
                resp.raise_for_status()
                res_json = resp.json()
                return res_json.get("transcript", "")
        except httpx.HTTPStatusError as e:
            raise SpeechError("Prisma", f"HTTP {e.response.status_code}: {e.response.text}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise SpeechError("Prisma", f"Network error: {e}") from e

    async def transcribe_file(
        self,
        audio_path: str | Path,
        language_code: str = "indic-auto",
    ) -> str:
        """Transcribe short audio file via REST endpoint."""
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        with open(path, "rb") as f:
            content = f.read()
        return await self.transcribe_bytes(content, filename=path.name, language_code=language_code)

    async def stream(
        self,
        pcm_chunks: AsyncIterator[bytes],
        language_code: str = "indic-auto",
    ) -> AsyncIterator[str]:
        """Stream raw PCM audio chunks over WSS (V1) with REST fallback."""
        if not self.api_key:
            raise SpeechError("Prisma", "GNANI_API_KEY is not configured")

        import websockets

        format_val = self.mode.lower().replace("-", "").replace("_", "")
        ws_url = f"{PRISMA_WS_URL}?model=prisma-v3.0&language_code={language_code}&format={format_val}"
        headers = {"X-API-Key-ID": self.api_key}

        accumulated = bytearray()
        try:
            async with websockets.connect(ws_url, additional_headers=headers) as ws:
                async for chunk in pcm_chunks:
                    accumulated.extend(chunk)
                    await ws.send(chunk)
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.1)
                        data = json.loads(msg)
                        if "transcript" in data:
                            yield data["transcript"]
                    except asyncio.TimeoutError:
                        pass
                await ws.send(b'{"eof": true}')
                # Final response
                final_msg = await ws.recv()
                data = json.loads(final_msg)
                if "transcript" in data:
                    yield data["transcript"]
        except Exception as e:
            logger.warning("Prisma WSS stream failed (%s), falling back to REST transcription", e)
            if accumulated:
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(accumulated)
                transcript = await self.transcribe_bytes(wav_io.getvalue(), language_code=language_code)
                if transcript:
                    yield transcript
