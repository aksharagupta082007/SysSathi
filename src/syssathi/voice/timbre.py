"""Timbre text-to-speech client for REST and SSE/chunked synthesis."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from syssathi.host.config import GNANI_API_KEY, TIMBRE_VOICE

logger = logging.getLogger(__name__)

TIMBRE_REST_URL = "https://api.vachana.ai/api/v1/tts/inference"
TIMBRE_SSE_URL = "https://api.vachana.ai/api/v1/tts/sse"


class TimbreClient:
    """Client for Gnani Timbre v3.0 TTS."""

    def __init__(self, api_key: str | None = None, voice: str | None = None) -> None:
        self.api_key = api_key or GNANI_API_KEY
        self.voice = voice or TIMBRE_VOICE or "Shivani"

    async def synthesize_sentence(
        self,
        text: str,
        language: str = "hi-IN",
        speed: float = 1.0,
    ) -> bytes:
        """Synthesize a complete sentence to WAV bytes via REST inference."""
        headers = {
            "Content-Type": "application/json",
            "X-API-Key-ID": self.api_key,
        }
        payload = {
            "text": text,
            "model": "timbre-v3.0",
            "voice": self.voice,
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(TIMBRE_REST_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content

