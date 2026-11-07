"""Probe script for Gnani AI Timbre TTS and Prisma STT APIs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from syssathi.host.config import GNANI_API_KEY, PRISMA_MODE, TIMBRE_VOICE


def probe_timbre(api_key: str, voice: str) -> None:
    """Synthesize 'Ek second, check karta hoon' in latin and devanagari_mixed."""
    url = "https://api.vachana.ai/api/v1/tts/inference"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key-ID": api_key,
    }

    samples = [
        ("latin", "Ek second, check karta hoon", "timbre_latin.wav"),
        ("devanagari_mixed", "एक second, check करता हूँ", "timbre_devanagari.wav"),
    ]

    out_dir = PROJECT_ROOT / "logs" / "audio_probes"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Probing Timbre TTS (Voice: {voice}) ---")
    for style, text, filename in samples:
        payload = {
            "text": text,
            "model": "timbre-v3.0",
            "voice": voice,
            "language": "hi-IN",
            "speed": 1.0,
            "audio_config": {
                "encoding": "linear_pcm",
                "container": "wav",
                "sample_rate": 48000,
                "num_channels": 1,
                "sample_width": 2,
            },
        }

        print(f"Requesting [{style}]: '{text}' ...")
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                out_path = out_dir / filename
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                print(f"  -> Saved {len(resp.content)} bytes to {out_path}")
            else:
                print(f"  -> Error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"  -> Request failed: {e}")


def probe_prisma(api_key: str, audio_path: str, mode: str) -> None:
    """Transcribe an audio file using Prisma v3.0 REST API."""
    url = "https://api.vachana.ai/stt/v3"
    headers = {
        "X-API-Key-ID": api_key,
    }

    path = Path(audio_path)
    if not path.exists():
        print(f"Audio file not found: {path}")
        return

    print(f"\n--- Probing Prisma STT (Mode: {mode}) ---")
    print(f"Transcribing file: {path} ...")

    with open(path, "rb") as f:
        files = {"audio_file": (path.name, f, "audio/wav")}
        data = {
            "model": "prisma-v3.0",
            "language_code": "indic-auto",
            "format": mode.lower(),
            "keyterms": "Chrome, Teams, Spotify, OneDrive, Edge, Zoom",
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, data=data, files=files, headers=headers)
            if resp.status_code == 200:
                res_json = resp.json()
                print("  -> Transcript:", res_json.get("transcript"))
                print(f"  -> Full response: {res_json}")
            else:
                print(f"  -> Error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"  -> Request failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gnani AI API Probe Script")
    parser.add_argument("--audio", help="Optional audio file path to test Prisma STT")
    args = parser.parse_args()

    api_key = GNANI_API_KEY
    if not api_key:
        print("GNANI_API_KEY is not set in .env")
        sys.exit(1)

    voice = TIMBRE_VOICE or "Shivani"
    mode = PRISMA_MODE or "Code-mix"

    # 1. Probe Timbre
    probe_timbre(api_key, voice)

    # 2. Probe Prisma if audio file specified
    if args.audio:
        probe_prisma(api_key, args.audio, mode)
    else:
        # Check if we generated timbre_latin.wav and probe with that as demo
        demo_audio = PROJECT_ROOT / "logs" / "audio_probes" / "timbre_latin.wav"
        if demo_audio.exists():
            probe_prisma(api_key, str(demo_audio), mode)


if __name__ == "__main__":
    main()

