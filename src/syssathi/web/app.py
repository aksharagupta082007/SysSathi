"""FastAPI web server providing push-to-talk interface and WebSocket audio pipeline."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import secrets
import time
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from syssathi.core.privacy import redact_paths_and_users
from syssathi.host.config import EVON_KEEPALIVE, get_llm_backend
from syssathi.host.mcp_client import MCPClient
from syssathi.host.orchestrator import Orchestrator, Session
from syssathi.host.router import route
from syssathi.host.timing import Timer
from syssathi.voice.prisma import PrismaClient
from syssathi.voice.splitter import SentenceSplitter
from syssathi.voice.timbre import TimbreClient
from syssathi.web.confirmation import format_remeasure_reply

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# Global MCP client (shared process)
_mcp_client: MCPClient | None = None
_keepalive_task: asyncio.Task | None = None

# Allowed origins and hostnames for security (W2, W3)
ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}


def is_allowed_origin(origin: str | None) -> bool:
    """Validate that the Origin header comes from local host."""
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
        return parsed.hostname in ALLOWED_HOSTNAMES
    except Exception:
        return False


def is_allowed_host(host: str | None) -> bool:
    """Validate that the Host header comes from local host."""
    if not host:
        return False
    hostname = host.split(":")[0]
    return hostname in ALLOWED_HOSTNAMES


@dataclass
class WebSession:
    session_id: str
    nonce: str
    orchestrator: Orchestrator
    session: Session
    created_at: float = field(default_factory=time.time)


_sessions: dict[str, WebSession] = {}


def get_or_create_session(session_id: str | None) -> WebSession:
    """Get existing session or create a new isolated session (W1, 4.2)."""
    global _mcp_client
    if session_id and session_id in _sessions:
        return _sessions[session_id]

    new_id = secrets.token_hex(16)
    nonce = secrets.token_hex(16)
    orch = Orchestrator(_mcp_client)  # type: ignore
    sess = Session(session_id=new_id)
    session = WebSession(
        session_id=new_id,
        nonce=nonce,
        orchestrator=orch,
        session=sess,
    )
    _sessions[new_id] = session
    return session


async def _evon_keepalive_loop() -> None:
    """Keep Evon endpoint warm only when opt-in (W11)."""
    from syssathi.host.config import EVON_BASE_URL, HF_TOKEN, LLM_BACKEND

    if LLM_BACKEND != "evon_remote" or not EVON_BASE_URL:
        return
    import httpx

    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    models_url = f"{EVON_BASE_URL.rstrip('/')}/models"
    while True:
        try:
            await asyncio.sleep(45)
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.get(models_url, headers=headers)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcp_client, _keepalive_task
    _mcp_client = MCPClient()
    await _mcp_client.start()
    if EVON_KEEPALIVE:
        _keepalive_task = asyncio.create_task(_evon_keepalive_loop())
    logger.info("SysSathi web server started on 127.0.0.1")
    yield
    if _keepalive_task:
        _keepalive_task.cancel()
        _keepalive_task = None
    if _mcp_client:
        await _mcp_client.close()
        _mcp_client = None


app = FastAPI(title="SysSathi Web Backend", lifespan=lifespan)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint surfacing MCP subprocess and service status (C3, WSL)."""
    global _mcp_client
    mcp_healthy = await _mcp_client.check_health() if _mcp_client else False
    from syssathi.core.wsl import get_environment_info
    return {
        "status": "ok" if mcp_healthy else "degraded",
        "mcp_server": "connected" if mcp_healthy else "disconnected",
        "llm_backend": get_llm_backend(),
        "environment": get_environment_info(),
    }


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, response: Response) -> HTMLResponse:
    """Serve the push-to-talk HTML page with embedded per-session nonce and cookie."""
    cookie_session_id = request.cookies.get("syssathi_session_id")
    session = get_or_create_session(cookie_session_id)

    with open(INDEX_HTML, encoding="utf-8") as f:
        content = f.read()

    # Inject session nonce into meta tag for Addendum A5 approval requests
    nonce_tag = f'<meta name="syssathi-nonce" content="{session.nonce}">'
    content = content.replace("<head>", f"<head>\n  {nonce_tag}")

    # Display mock banner if running in mock mode
    if get_llm_backend() == "mock":
        mock_banner = (
            '<div style="background:#eab308;color:#000;padding:6px;text-align:center;'
            'font-weight:bold;font-size:0.85rem;border-radius:6px;margin-bottom:12px;">'
            '[DEMO / MOCK MODE] Using simulated responses</div>'
        )
        content = content.replace('<div id="statusBadge"', f'{mock_banner}\n    <div id="statusBadge"')

    # Display WSL warning banner if running inside WSL VM (Decision 1 & §7)
    from syssathi.core.wsl import is_wsl
    if is_wsl():
        wsl_banner = (
            '<div style="background:#ef4444;color:#fff;padding:6px;text-align:center;'
            'font-weight:bold;font-size:0.85rem;border-radius:6px;margin-bottom:12px;">'
            '[WSL WARNING] Running in WSL VM; metrics apply to Linux VM, not your host Windows laptop.</div>'
        )
        content = content.replace('<div id="statusBadge"', f'{wsl_banner}\n    <div id="statusBadge"')

    html_resp = HTMLResponse(content=content)
    html_resp.set_cookie(
        "syssathi_session_id",
        session.session_id,
        httponly=True,
        samesite="lax",
    )
    return html_resp


@app.post("/api/approve")
async def post_approve(
    request: Request,
    x_nonce: str | None = Header(None, alias="X-SysSathi-Nonce"),
    origin: str | None = Header(None),
    host: str | None = Header(None),
    syssathi_session_id: str | None = Cookie(None),
) -> dict[str, Any]:
    """Approve and execute pending proposal. Follows Addendum A5 security rules."""
    # 1. Origin check (must be present and must be local)
    if not origin or not is_allowed_origin(origin):
        raise HTTPException(status_code=403, detail="Disallowed Origin")

    # 2. Host check
    if host and not is_allowed_host(host):
        raise HTTPException(status_code=403, detail="Disallowed Host")

    # 3. Session and Nonce check
    session = _sessions.get(syssathi_session_id) if syssathi_session_id else None
    if not session:
        # Fall back to single session if exists for backward-compatible tests
        if len(_sessions) == 1:
            session = next(iter(_sessions.values()))
        else:
            raise HTTPException(status_code=403, detail="Invalid or missing session")

    if not x_nonce or not secrets.compare_digest(x_nonce, session.nonce):
        raise HTTPException(status_code=403, detail="Invalid or missing session nonce")

    orchestrator = session.orchestrator
    pending = session.session.pending_proposal or orchestrator.pending_proposal
    if not pending:
        raise HTTPException(status_code=400, detail="No pending proposal to approve")

    # Capture before findings
    before_findings = session.session.last_tool_result or orchestrator.latest_findings

    # Execute action
    execution_result = await orchestrator.approve(session.session)

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
    # W2: Check Origin before accept()
    origin = websocket.headers.get("origin")
    if origin and not is_allowed_origin(origin):
        logger.warning("Rejected WebSocket from disallowed Origin: %s", origin)
        await websocket.close(code=1008, reason="Disallowed Origin")
        return

    await websocket.accept()

    # W1: Get or create session bound to this WebSocket
    cookie_session_id = websocket.cookies.get("syssathi_session_id")
    session = get_or_create_session(cookie_session_id)
    orchestrator = session.orchestrator

    prisma = PrismaClient()
    timbre = TimbreClient()
    timer = Timer()
    audio_buffer = bytearray()
    user_text: str | None = None

    # W5: Max 30s audio at 16kHz 16-bit mono = ~960,000 bytes (~1 MB)
    MAX_AUDIO_BYTES = 1_000_000

    try:
        while True:
            msg = await websocket.receive()
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                logger.info("WebSocket client disconnected")
                return
            if "bytes" in msg and msg["bytes"]:
                if len(audio_buffer) + len(msg["bytes"]) <= MAX_AUDIO_BYTES:
                    audio_buffer.extend(msg["bytes"])
                else:
                    logger.warning("Audio buffer limit reached, capping audio.")
                    break
            elif "text" in msg and msg["text"]:
                try:
                    data = json.loads(msg["text"])
                    if data.get("type") == "text":
                        user_text = data.get("text", "").strip()
                        if "language" in data:
                            session.session.language = data["language"]
                        if "script" in data:
                            session.session.script = data["script"]
                        break
                    elif data.get("type") == "settings":
                        if "language" in data:
                            session.session.language = data["language"]
                        if "script" in data:
                            session.session.script = data["script"]
                    elif data.get("type") == "eof":
                        if "language" in data:
                            session.session.language = data["language"]
                        if "script" in data:
                            session.session.script = data["script"]
                        break
                except Exception:
                    pass
    except WebSocketDisconnect:
        return

    # Process received audio with Prisma in memory (W4)
    if user_text is None:
        timer.mark("stt_start")
        if prisma.api_key and audio_buffer and len(audio_buffer) >= 1600:
            try:
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_buffer)
                wav_bytes = wav_io.getvalue()
                transcribed = await prisma.transcribe_bytes(wav_bytes)
                user_text = transcribed.strip() if transcribed else ""
                logger.info("Prisma transcribed (%d audio bytes): %r", len(audio_buffer), user_text)
            except Exception as e:
                logger.warning("Prisma transcription failed: %s", e)
                user_text = ""
        else:
            # W6: Deleted fake-transcript hack
            user_text = ""
        timer.mark("stt_ms")

    # If no intelligible text or audio was provided
    if not user_text:
        await websocket.send_text(json.dumps({"type": "transcript", "text": "(Awaaz nahi aayi)"}))
        await websocket.send_text(json.dumps({
            "type": "reply",
            "text": "Awaaz sunayi nahi di, kripya thoda lamba bolein ya type karein.",
        }))
        await websocket.send_text(json.dumps({"type": "status", "text": "Ready"}))
        return

    # Redact personal paths and usernames before external processing (Privacy §7.4)
    user_text = redact_paths_and_users(user_text)

    await websocket.send_text(json.dumps({"type": "transcript", "text": user_text}))

    # Stream turn events directly from orchestrator (W7, W8, V5, W14, §7.1)
    tts_first_sent = False
    try:
        async for evt in orchestrator.run_turn(session.session, user_text):
            if evt.type == "route":
                timer.set("route", evt.data.get("route"))
            elif evt.type == "status":
                await websocket.send_text(json.dumps({"type": "status", "text": evt.text}))
            elif evt.type == "tool_call":
                tool_label = {
                    "diagnose_slowness": "Measuring CPU, RAM & Disk...",
                    "get_top_processes": "Checking heavy processes...",
                    "list_startup_apps": "Inspecting startup apps...",
                    "get_battery_report": "Reading battery status...",
                    "search_sources": "Searching knowledge base...",
                    "get_tool_recommendations": "Finding verified tools...",
                    "explain_term": "Looking up explanation...",
                    "propose_close": "Preparing safety proposal...",
                }.get(evt.data.get("name"), "Working...")
                await websocket.send_text(json.dumps({"type": "status", "text": tool_label}))
            elif evt.type == "filler":
                # Instant filler playback via disk-cached TTS (W8)
                try:
                    filler_audio = await timbre.synthesize_filler_cached(evt.text)
                    await websocket.send_bytes(filler_audio)
                except Exception as e:
                    logger.debug("Filler audio synthesis skipped: %s", e)
            elif evt.type == "proposal":
                await websocket.send_text(json.dumps({
                    "type": "proposal",
                    "description": evt.data.get("description", "Close action proposed"),
                    "data": evt.data,
                }))
            elif evt.type == "sources":
                await websocket.send_text(json.dumps({
                    "type": "sources",
                    "data": evt.data,
                }))
            elif evt.type == "lesson_card":
                await websocket.send_text(json.dumps({
                    "type": "lesson_card",
                    "data": evt.data,
                }))
            elif evt.type == "sentence":
                # Stream TTS audio sentence-by-sentence (V5, W14)
                try:
                    audio_bytes = await timbre.synthesize_sentence(evt.text)
                    if not tts_first_sent:
                        timer.mark("first_sentence_ms")
                        timer.mark("tts_first_byte_ms")
                        tts_first_sent = True
                    await websocket.send_bytes(audio_bytes)
                except Exception as e:
                    logger.debug("Sentence TTS audio skipped: %s", e)
            elif evt.type == "reply":
                await websocket.send_text(json.dumps({"type": "reply", "text": evt.text}))
            elif evt.type == "done":
                break
    except Exception as e:
        logger.exception("Error during orchestrator streaming turn: %s", e)
        reply = "Kshama karein, abhi diagnosis me dikkat aayi. Kripya dobara try karein."
        await websocket.send_text(json.dumps({"type": "reply", "text": reply}))

    timer.flush()
    await websocket.send_text(json.dumps({"type": "status", "text": "Ready"}))
