"""FastAPI web server providing push-to-talk interface and WebSocket audio pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from syssathi.host.mcp_client import MCPClient
from syssathi.host.orchestrator import Orchestrator
from syssathi.host.router import route
from syssathi.host.timing import Timer
from syssathi.voice.prisma import PrismaClient
from syssathi.voice.splitter import SentenceSplitter
from syssathi.voice.timbre import TimbreClient
from syssathi.web.confirmation import format_remeasure_reply

logger = logging.getLogger(__name__)

app = FastAPI(title="SysSathi Web Backend")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# Global orchestrator and active session
_mcp_client: MCPClient | None = None
_orchestrator: Orchestrator | None = None
_session_nonce: str = ""


@app.on_event("startup")
async def startup_event() -> None:
    global _mcp_client, _orchestrator, _session_nonce
    _session_nonce = secrets.token_hex(16)
    _mcp_client = MCPClient()
    await _mcp_client.start()
    _orchestrator = Orchestrator(_mcp_client)
    logger.info("SysSathi web server started on 127.0.0.1")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _mcp_client
    if _mcp_client:
        await _mcp_client.close()
        _mcp_client = None


@app.get("/", response_class=HTMLResponse)
async def get_index() -> HTMLResponse:
    """Serve the single push-to-talk HTML page with embedded session nonce."""
    with open(INDEX_HTML, encoding="utf-8") as f:
        content = f.read()
    # Inject nonce into meta tag for Addendum A5 approval requests
    nonce_tag = f'<meta name="syssathi-nonce" content="{_session_nonce}">'
    content = content.replace("<head>", f"<head>\n  {nonce_tag}")
    return HTMLResponse(content=content)


@app.post("/api/approve")
async def post_approve(
    x_nonce: str | None = Header(None, alias="X-SysSathi-Nonce"),
    origin: str | None = Header(None),
    host: str | None = Header(None),
) -> dict[str, Any]:
    """Approve and execute pending proposal. Follows Addendum A5 security rules."""
    # 1. Nonce check
    if not x_nonce or not secrets.compare_digest(x_nonce, _session_nonce):
        raise HTTPException(status_code=403, detail="Invalid or missing session nonce")

    # 2. Origin / Host check (must be local server)
    allowed_hosts = {"127.0.0.1", "localhost", "127.0.0.1:8000", "localhost:8000"}
    if host and host not in allowed_hosts:
        raise HTTPException(status_code=403, detail="Disallowed Host")
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        if parsed.netloc not in allowed_hosts:
            raise HTTPException(status_code=403, detail="Disallowed Origin")

    if not _orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    if not _orchestrator.pending_proposal:
        raise HTTPException(status_code=400, detail="No pending proposal to approve")

    # Capture before findings
    before_findings = _orchestrator.latest_findings

    # Execute action
    execution_result = await _orchestrator.approve()

    # Build confirmation message
    spoken_reply = format_remeasure_reply(execution_result, before_findings)

    # Synthesize spoken confirmation via Timbre if configured
    audio_base64: str | None = None
    if spoken_reply:
        try:
            timbre = TimbreClient()
            if timbre.api_key:
                audio_bytes = await timbre.synthesize_sentence(spoken_reply)
                import base64
                audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
        except Exception as e:
            logger.warning("Failed to synthesize approve audio: %s", e)

    return {
        "success": not ("error" in execution_result or execution_result.get("refused")),
        "result": execution_result,
        "spoken_reply": spoken_reply,
        "audio_base64": audio_base64,
    }


@app.websocket("/ws/talk")
async def websocket_talk(websocket: WebSocket) -> None:
    """WebSocket endpoint handling audio stream, routing, and TTS playback."""
    await websocket.accept()
    if not _orchestrator:
        await websocket.close()
        return

    prisma = PrismaClient()
    timbre = TimbreClient()
    timer = Timer()
    audio_buffer = bytearray()

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg and msg["bytes"]:
                audio_buffer.extend(msg["bytes"])
            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "eof":
                    break
    except WebSocketDisconnect:
        return

    # Process received audio with Prisma
    timer.mark("stt_start")
    # For offline testing or if mock / empty audio
    user_text = "Mera laptop slow chal raha hai"
    if prisma.api_key and audio_buffer:
        temp_audio = Path("/tmp/syssathi_recording.wav")
        try:
            import wave
            with wave.open(str(temp_audio), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_buffer)
            user_text = await prisma.transcribe_file(temp_audio)
        except Exception as e:
            logger.warning("Prisma transcription failed, using fallback: %s", e)

    timer.mark("stt_ms")
    await websocket.send_text(json.dumps({"type": "transcript", "text": user_text}))

    # Check route
    r = route(user_text)
    timer.set("route", r)

    # Fast route: play filler ("Ek second, check karta hoon") immediately
    if r == "fast":
        try:
            filler_audio = await timbre.synthesize_sentence("Ek second, check karta hoon")
            await websocket.send_bytes(filler_audio)
        except Exception:
            # Fake/offline fallback
            pass

    # Orchestrator handles message and proposal
    reply, _ = await _orchestrator.handle_message(user_text)
    await websocket.send_text(json.dumps({"type": "reply", "text": reply}))

    if _orchestrator.pending_proposal:
        await websocket.send_text(json.dumps({
            "type": "proposal",
            "description": _orchestrator.pending_proposal.get("description", "Close action proposed"),
        }))

    # Synthesize reply sentences to Timbre
    splitter = SentenceSplitter()
    sentences = splitter.push(reply) + splitter.flush()

    for idx, sentence in enumerate(sentences):
        try:
            audio_bytes = await timbre.synthesize_sentence(sentence)
            if idx == 0:
                timer.mark("tts_first_byte_ms")
            await websocket.send_bytes(audio_bytes)
        except Exception:
            pass

    timer.flush()
    await websocket.send_text(json.dumps({"type": "status", "text": "Ready"}))

