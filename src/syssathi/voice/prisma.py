"""Prisma speech-to-text client for REST and WebSocket streaming."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from syssathi.host.config import GNANI_API_KEY, KEYTERMS_LIST, PRISMA_MODE

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

    async def transcribe_file(self, audio_path: str | Path) -> str:
        """Transcribe short audio file via REST endpoint."""
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        headers = {"X-API-Key-ID": self.api_key}
        format_val = self.mode.lower().replace("-", "").replace("_", "")
        data = {
            "model": "prisma-v3.0",
            "language_code": "indic-auto",
            "format": format_val,
            "keyterms": ", ".join(self.keyterms),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(path, "rb") as f:
                files = {"audio_file": (path.name, f, "audio/wav")}
                resp = await client.post(PRISMA_REST_URL, data=data, files=files, headers=headers)
                resp.raise_for_status()
                res_json = resp.json()
                return res_json.get("transcript", "")

