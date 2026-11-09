"""Timbre text-to-speech client for REST and cached synthesis (V3, V4, W8)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from syssathi.host.config import GNANI_API_KEY, TIMBRE_VOICE, get_logs_dir
from syssathi.voice.errors import SpeechError

logger = logging.getLogger(__name__)

TIMBRE_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"
TIMBRE_SSE_URL = "https://api.vachana.ai/api/v1/tts/sse"


class TimbreClient:
    """Client for Gnani Timbre v3.0 TTS with persistent keep-alive and filler caching."""

    def __init__(self, api_key: str | None = None, voice: str | None = None) -> None:
        self.api_key = api_key or GNANI_API_KEY
        self.voice = voice or TIMBRE_VOICE or "Shivani"
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Reuse persistent httpx.AsyncClient for keep-alive TLS connection (V3)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close keep-alive connection."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> TimbreClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def synthesize_sentence(
        self,
        text: str,
        language: str = "hi-IN",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> bytes:
        """Synthesize a complete sentence to WAV bytes via REST inference."""
        if not self.api_key:
            raise SpeechError("Timbre", "GNANI_API_KEY is not configured")

        chosen_voice = voice or self.voice
        headers = {
            "Content-Type": "application/json",
            "X-API-Key-ID": self.api_key,
        }
        payload = {
            "text": text,
            "model": "timbre-v3.0",
            "voice": chosen_voice,
            "language": language,
            "speed": speed,
            "audio_config": {
                "encoding": "linear_pcm",
                "container": "wav",
                "sample_rate": 48000,
                "num_channels": 1,
                "sample_width": 2,
            },
        }

        client = self._get_client()
        try:
            resp = await client.post(TIMBRE_REST_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError as e:
            raise SpeechError("Timbre", f"HTTP {e.response.status_code}: {e.response.text}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise SpeechError("Timbre", f"Network error: {e}") from e

    async def synthesize_filler_cached(
        self,
        text: str,
        language: str = "hi-IN",
        voice: str | None = None,
    ) -> bytes:
        """Synthesize filler phrase with disk caching to eliminate TTS latency (W8)."""
        chosen_voice = voice or self.voice
        cache_dir = get_logs_dir() / "filler_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        key = hashlib.sha256(f"{text}_{language}_{chosen_voice}".encode("utf-8")).hexdigest()[:16]
        cache_file = cache_dir / f"filler_{key}.wav"

        if cache_file.is_file():
            try:
                return cache_file.read_bytes()
            except OSError:
                pass

        audio_bytes = await self.synthesize_sentence(text, language=language, voice=chosen_voice)
        try:
            cache_file.write_bytes(audio_bytes)
        except OSError:
            pass
        return audio_bytes
