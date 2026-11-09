"""Typed speech exceptions for Prisma STT and Timbre TTS (V4)."""

from __future__ import annotations


class SpeechError(Exception):
    """Raised when an STT or TTS speech service fails or is unreachable."""

    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{service} error: {message}")
        self.service = service
        self.message = message
        self.status_code = status_code

