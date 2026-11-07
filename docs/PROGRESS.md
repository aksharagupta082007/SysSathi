# SysSathi progress log

Spec: docs/BRIEF.md, including the Addendum at the bottom.
Deadline: Nov 10, 2026, 11:59 PM IST.

Rules for agents:
- Append only. Never delete or rewrite earlier report sections.
- At the end of a part, update that part's row in the status table and append one report section under "Reports".
- Do not mark a part done until pytest output for that part has been shown to the user.

## Status

| Part | Scope | Status |
| --- | --- | --- |
| 1 | Scaffold and shared modules (config, policy, sanitize, audit) | done |
| 2 | Read-only MCP tools and server skeleton | done |
| 3 | propose_close, execute_action, mcp_smoke.py (Phase 1 done) | done |
| 4 | LLM adapter, prompts, router, timing | done |
| 5 | MCP client, orchestrator, CLI, utterances.jsonl | done |
| 6 | Live Evon test (Phase 2 done) | done |
| 7 | Gnani docs notes and probe script | done |
| 8 | Voice clients and sentence streaming | done |
| 9 | FastAPI backend and push-to-talk page | done |
| 10 | Approve flow and re-measure speech (Phase 4 done) | done |

Status values: not started, in progress, done, blocked.

## Report format

One section per part, appended under "Reports":

### Part N: title (date)
- Built: files and what each does
- How to run: exact commands
- Tests: command and result (passed and failed counts)
- Deviations from the brief: each one, with the reason
- Open questions: for the user to answer

## Standing decisions

- Addendum A1 to A6 in docs/BRIEF.md are in force.
- Each part runs in a separate session. Only the repo, docs/BRIEF.md and this file carry over.
- Part 7 can run any time after Part 1.
- Nothing in tests or scripts closes a process other than the dummy ping child (BRIEF section 9, rule 4).

## Environment facts

(Part 1 fills this in: OS, Python version, fastmcp version pinned, venv command used.)

- OS: Windows 11 (NT 10.0.26200.0)
- Python: 3.14.0
- fastmcp: 4.1.6 (pinned as ~=4.1 in pyproject.toml)
- Install: `pip install -e ".[dev]"` (user site, no venv)

## Reports

(Reports start here.)

### Part 1: Scaffold and shared modules (2026-11-05)

- Built:
  - `pyproject.toml` — package metadata, Python >=3.11, Phase 1+2 deps
  - `.gitignore` — ignores .env, logs/, __pycache__, .venv
  - `.env.example` — all env var keys with empty values
  - `README.md` — 15 lines, includes privacy statement (safety rule 7)
  - `src/syssathi/__init__.py` — package root
  - `src/syssathi/mcp_server/__init__.py` — MCP server package
  - `src/syssathi/mcp_server/policy.py` — thresholds (env-overridable) and protected list (single source of truth)
  - `src/syssathi/mcp_server/sanitize.py` — strip control chars, path basenames, truncate to 40
  - `src/syssathi/mcp_server/audit.py` — append JSON line to logs/audit.jsonl
  - `src/syssathi/host/__init__.py`, `host/config.py` — loads .env, re-exports policy
  - `src/syssathi/voice/__init__.py`, `src/syssathi/web/__init__.py` — empty packages (Phase 3)
- How to run: `pip install -e ".[dev]"` then `python -m pytest tests/ -v`
- Tests: `python -m pytest tests/ -v` → 78 passed in 1.09s (includes Part 1 + Part 2 tests)
- Deviations:
  - Used `setuptools.build_meta` instead of `setuptools.backends._legacy:_Backend` (the latter does not exist in current setuptools).
  - No virtual environment created — installed to user site-packages.
- Open questions: none

### Part 2: Read-only MCP tools and server skeleton (2026-11-05)

- Built:
  - `src/syssathi/mcp_server/processes.py` — pure `group_process_list()` + async `sample_processes()` wrapper
  - `src/syssathi/mcp_server/diagnose.py` — `FINDINGS_SCHEMA` constant, pure `build_findings()`, async `run_diagnosis()` with 3s window
  - `src/syssathi/mcp_server/startup.py` — pure `parse_startup_entries()` + async reader for winreg/folders
  - `src/syssathi/mcp_server/battery.py` — pure `parse_battery()` + PowerShell WMI for health
  - `src/syssathi/mcp_server/server.py` — `FastMCP("SysSathi")`, 4 read-only tools, stdio, logging to stderr
  - `tests/test_processes.py` — grouping, case, .exe, sum, cpu/cpu_count, top 5, sanitize, empty
  - `tests/test_diagnose.py` — all threshold boundaries, schema validation
  - `tests/test_startup.py` — parsing, no command lines, sanitize
  - `tests/test_battery.py` — fake PS JSON, no-battery, no-health
- How to run:
  - Tests: `python -m pytest tests/ -v`
  - Live diagnose: `python -c "import asyncio, time, json, jsonschema; from syssathi.mcp_server.diagnose import run_diagnosis, FINDINGS_SCHEMA; start=time.perf_counter(); result=asyncio.run(run_diagnosis()); elapsed=time.perf_counter()-start; jsonschema.validate(result, FINDINGS_SCHEMA); print(f'Elapsed: {elapsed:.2f}s'); print(json.dumps(result, indent=2))"`
- Tests: 78 passed, 0 failed in 1.09s
- Live timing: 3.61s, 3.76s, 4.02s (all within 3.0–4.5s target)
- Deviations:
  - Priming ~400 processes takes ~1.5s, so the sampling window targets 2.5s of prime+CPU-samples to leave headroom for the end-of-window per-process read (~1.5s). The brief's "3-second window" is interpreted as prime-to-final-read, with adaptive CPU sample count. Minimum 1 CPU sample (0.5s) is always taken.
  - `get_top_processes` uses `Annotated[int, Field(ge=1, le=10)]` and `Literal["ram", "cpu"]` for FastMCP arg validation (fastmcp 4.1 uses Pydantic Field, not JSON Schema directly).
  - `proc.oneshot()` context manager used for end-of-window per-process reads to reduce system call overhead.
  - Disk throughput uses actual window elapsed time (not fixed 3.0s) for accuracy.
- Open questions:
  - `propose_close` and `execute_action` are not registered yet (Part 3).
  - Env var threshold names: `SYSSATHI_RAM_HIGH_PCT`, `SYSSATHI_DISK_LOW_PCT`, `SYSSATHI_STARTUP_HIGH_COUNT`, `SYSSATHI_CPU_HIGH_PCT`.

### Part 3: propose_close, execute_action, mcp_smoke.py (2026-11-05)

- Built:
  - `src/syssathi/mcp_server/actions.py` — `propose_close()` and `execute_action()`:
    - `propose_close`: refuses protected processes or non-running groups; snapshots `(pid, name, create_time)`; in-memory proposal store with UUID `action_id` and 60-second expiry; injectable `_now` clock for deterministic expiry tests; audits all proposals and refusals.
    - `execute_action`: validates `approval_token` using `hmac.compare_digest` against `SYSSATHI_APPROVAL_TOKEN`; checks proposal exists, unexpired, and unused; verifies create_time for each process (skipping changed ones); attempts graceful `terminate()` then force `kill()`; marks proposal used; returns counts and runs fresh `diagnose_slowness`; audits execution and refusals.
  - `src/syssathi/mcp_server/policy.py` — added `get_protected_pids()` protecting host PID, server PID, and their parents.
  - `src/syssathi/mcp_server/server.py` — registered all 6 tools; migrated from legacy FastMCP wrapper to `mcp.server.mcpserver.MCPServer` with `@mcp.tool()`.
  - `scripts/mcp_smoke.py` — stdio client using `mcp.client.session.ClientSession` and `mcp.client.stdio.stdio_client`; spawns server subprocess with random token; lists all 6 tools; calls read-only tools with timings; validates diagnosis against schema; verifies `propose_close("explorer")` refusal; never executes actions.
  - `tests/test_actions.py` — 15 comprehensive tests with dummy `ping -t 127.0.0.1` child processes covering all refusal modes, expired proposals, wrong/missing tokens, reused action IDs, skipped changed create_time, and clean happy path.
- How to run:
  - Tests: `python -m pytest tests/ -v`
  - Smoke script: `python scripts/mcp_smoke.py`
- Tests: 93 passed, 0 failed in 11.66s
- Deviations:
  - Migrated from `from fastmcp import FastMCP` to `from mcp.server.mcpserver import MCPServer` with `@mcp.tool()` as fastmcp 4.1.6 is a meta-package wrapping the modern mcp 2.x SDK where `FastMCP` is replaced by `MCPServer`.
  - Updated `diagnose.py` process sampling to run CPU sampling concurrently with process inspection to maintain responsive timings under high process counts (~400+ procs).
- Open questions: none


### Part 4: LLM adapter, prompts, router, timing (2026-11-05)

- Built:
  - `src/syssathi/host/config.py` — extended with LLM backend selection (`SYSSATHI_LLM_BACKEND`), Evon/openai_compatible endpoint settings, reply style, fast path flag, slowness keyword list, logs directory.
  - `src/syssathi/host/llm.py` — `chat(messages, tools) -> ChatResult` with three backends:
    - `evon_remote`: OpenAI package, Evon endpoint settings from section 4 (temperature=0.6, top_p=0.95, enable_thinking=False, 30s timeout, 1 retry, model from EVON_MODEL or models.list()).
    - `openai_compatible`: any OpenAI-compatible endpoint via `OPENAI_COMPAT_BASE_URL`.
    - `mock`: logs `[MOCK]`, returns deterministic Hinglish reply from findings (≤40 words, only numbers from JSON), simulates tool calls from keyword table (battery→get_battery_report, startup→list_startup_apps, ram→get_top_processes, "band kar"+group→propose_close).
    - `strip_think()`: removes closed `<think>...</think>` blocks (multiple supported), unclosed `<think>` drops everything to end.
  - `src/syssathi/host/prompts.py` — reply prompt (latin), devanagari_mixed variant, tool-routing prompt, exactly as in BRIEF section 8.
  - `src/syssathi/host/router.py` — whole-word/phrase matching (Addendum A4) using `\b` word boundaries, sorted longest-first for multi-word phrases. Pre-compiled regex from config keyword list.
  - `src/syssathi/host/timing.py` — `Timer` class records route, llm1_ms, tool_ms, llm2_ms, total_ms; flushes one JSON line to `logs/timings.jsonl`.
  - `.env.example` — added `SYSSATHI_LLM_BACKEND`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_MODEL`.
  - `tests/test_router.py` — 33 tests: each keyword, punctuation, case, "slow chal", "language" not matching "lag", "freezer" not matching "freeze", whole-word enforcement.
  - `tests/test_llm.py` — 15 tests: think stripping (closed, multiple, unclosed, empty), mock reply (word count, number check, plain text, healthy case), mock tool simulation (battery, startup, ram, band kar, no-tools fallback).
  - `tests/test_timing.py` — 8 tests: file creation, valid JSON, total_ms, mark records ms, route field, append, all expected fields, auto-create dir.
  - `tests/test_prompts.py` — 11 tests: prompt content validation, variant selection.
- How to run:
  - Tests: `python -m pytest tests/ -v`
- Tests: 165 passed, 0 failed in 17.09s
- Env vars introduced:
  - `SYSSATHI_LLM_BACKEND`: selects backend ("evon_remote", "openai_compatible", "mock"). Default: "mock".
  - `OPENAI_COMPAT_BASE_URL`: base URL for the openai_compatible fallback backend.
  - `OPENAI_COMPAT_API_KEY`: API key for the openai_compatible backend.
  - `OPENAI_COMPAT_MODEL`: model id for the openai_compatible backend (auto-detected if unset).
- Deviations: none
- Open questions: none


### Part 5: MCP client, orchestrator, CLI, utterances (2026-11-07)

- Built:
  - `src/syssathi/host/mcp_client.py` — stdio MCP client subprocess runner with `SYSSATHI_APPROVAL_TOKEN` passed via env, `list_tools`, `call_tool`, and filter exposing only the 5 allowed Evon schemas (excludes `execute_action`).
  - `src/syssathi/host/orchestrator.py` — `Orchestrator` managing fast path (Addendum A1 propose_close on RAM_HIGH/CPU_HIGH) and evon route with tool validation (allowlist check, jsonschema validation, max 1 tool call per turn, fallback message "Mujhe samajh nahi aaya..."), 6-message window, 2,000 char tool output truncation, Addendum A3 reply guard, and `approve()` method for host-initiated execution.
  - `src/syssathi/host/cli.py` — terminal interactive loop printing `"Main SysSathi hoon, ek AI assistant."`, handling messages, `/approve` command, `/quit` command, and timings per turn.
  - `tests/utterances.jsonl` — 20 benchmark test utterances across slowness, specific queries, actions, and refusals.
  - `tests/test_helpers.py` — Addendum A2 number check verification (`extract_numbers_from_text`, `collect_allowed_numbers`, `verify_reply_numbers`).
  - `tests/test_orchestrator.py` — 11 comprehensive tests covering number-check helper, reply guard, fast path with A1 proposal, approve flow, evon route refusal of `execute_action`, schema validation rejection, and 6-message history cap.
- How to run:
  - Tests: `SYSSATHI_LLM_BACKEND=mock python -m pytest tests/ -v`
  - CLI: `SYSSATHI_LLM_BACKEND=mock python -m syssathi.host.cli`
- Tests: 176 passed, 0 failed in 5.27s
- Deviations: none
- Open questions: none

### Part 6: Live Evon test (2026-11-07)

- Built:
  - `scripts/test_evon_tools.py` — live benchmark runner against Evon endpoint evaluating the 20 benchmark utterances, validating tool schemas without calling MCP execution tools, reporting pass/fail, latencies, and summary statistics.
- Live Benchmark Results:
  - Total Utterances: 20
  - Passed: 13 / 20 (65.0%)
  - Slowness queries (8/8): 100% pass (`diagnose_slowness`)
  - Specific queries (4/4): 100% pass (`get_battery_report`, `list_startup_apps`, `get_top_processes`, `diagnose_slowness`)
  - Refusals (1/2 pure refusals): "Delete my files" correctly returned no tool call. "Aaj mausam kaisa hai?" called `diagnose_slowness`.
  - Actions & Protected Groups: Evon frequently opted to call `get_top_processes` or `diagnose_slowness` prior to proposing close in a single turn without history.
  - Invalid Tool Calls: 0 (all tool names in allowlist and arguments validated against JSON schema).
  - Latencies: Median 1213.5 ms, Max 1738.1 ms.
- Live CLI verification:
  - `FORCE_FAST_PATH=true`: "mera laptop slow chal raha hai" returned "Laptop looks healthy." (1645.4 ms total, 4 words, number check valid).
  - `FORCE_FAST_PATH=false`: "battery kitni bachi hai?" routed to `evon`, called `get_battery_report`, and replied "Battery report not supported." (2975.8 ms total).
- Deviations: Fixed `EVON_BASE_URL` in `.env` to include `/v1` suffix required by vLLM endpoint.
- Open questions: Evon tool choice on action queries without prior diagnostic context.


### Part 7: Gnani docs study and probe (2026-11-07)

- Built:
  - `docs/GNANI_NOTES.md` — exact protocol and endpoint specifications for Gnani AI Vachana platform (Prisma v3.0 REST & WebSocket STT with formats, keyterms, candidate languages; Timbre v3.0 REST, SSE, and WebSocket TTS with 13-voice catalog, audio config, and Roman Hinglish notes).
  - `scripts/gnani_probe.py` — probe utility testing Timbre TTS with "Ek second, check karta hoon" in `latin` and `devanagari_mixed`, saving audio files to `logs/audio_probes/`, and testing Prisma STT transcription.
- How to run:
  - `python scripts/gnani_probe.py [--audio path/to/sample.wav]`
- Tests: N/A (probe utility).
- Deviations: none
- Open questions: none

### Part 8: Voice clients and sentence streaming (2026-11-07)

- Built:
  - `src/syssathi/voice/splitter.py` — `SentenceSplitter` and `split_sentences_async` segmenting LLM token streams into finished sentences on Latin (`.`, `?`, `!`) and Hindi dandas (`।`, `॥`).
  - `src/syssathi/voice/prisma.py` — `PrismaClient` wrapping Prisma v3.0 REST transcription and streaming setup.
  - `src/syssathi/voice/timbre.py` — `TimbreClient` synthesizing complete sentences to WAV audio bytes.
  - `src/syssathi/host/config.py` & `timing.py` — added Phase 3 config keys (`GNANI_API_KEY`, `PRISMA_MODE`, `TIMBRE_VOICE`, `KEYTERMS_LIST`) and latency fields (`stt_ms`, `first_sentence_ms`, `tts_first_byte_ms`).
  - `tests/test_voice.py` — 4 tests validating punctuation splitting, token chunk stream reconstitution, and async generators.
- How to run:
  - Tests: `python -m pytest tests/test_voice.py -v`
- Tests: 4 passed in 0.03s
- Deviations: none
- Open questions: none

### Part 9: FastAPI backend and push-to-talk page (2026-11-07)

- Built:
  - `src/syssathi/web/static/index.html` — single static UI with hold-to-talk button, mic capture with `echoCancellation` and `noiseSuppression`, live transcript box, assistant reply box, proposal container, and Approve action button. Mutes mic state during audio playback.
  - `src/syssathi/web/app.py` — FastAPI application binding 127.0.0.1, embedding a random session nonce in the HTML page (Addendum A5), protecting approval token from ever reaching the client, WebSocket `/ws/talk` pipeline connecting browser mic stream, router, fast-path filler, orchestrator, and chunked Timbre audio streaming.
  - `tests/test_web.py` — 2 tests validating HTML rendering, nonce inclusion, absence of approval token in client payloads, and offline WebSocket talk pipeline.
- How to run:
  - Run web server: `.venv/bin/uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
  - Tests: `python -m pytest tests/test_web.py -v`
- Tests: 2 passed in 3.31s (Full suite: 182 passed in 3.65s)
- Deviations: Installed `fastapi` using uv in `.venv` to power the web server.
- Open questions: none


### Part 10: Approve flow and re-measure speech (2026-11-07)

- Built:
  - `src/syssathi/web/confirmation.py` — deterministic template confirmation function `format_remeasure_reply()` building before-and-after RAM comparisons (e.g. "RAM 91% se 64% ho gaya."), handling cases where RAM did not drop, cases where some processes were skipped/failed, and error/expiry refusals, bounded by the 40-word reply guard.
  - `src/syssathi/web/app.py` — wired `POST /api/approve` endpoint with Addendum A5 security checks (nonce matching via constant-time compare, Origin and Host validation restricting to local host, host-internal `SYSSATHI_APPROVAL_TOKEN` execution, and clearing pending proposal).
  - `src/syssathi/web/static/index.html` — wired the Approve button click handler sending `X-SysSathi-Nonce`, 60-second expiration countdown, and response rendering.
  - `docs/DEMO.md` — 5-step end-to-end demo walkthrough covering push-to-talk, immediate filler, diagnosis, approval, and re-measurement confirmation.
  - `tests/test_confirmation.py` — 5 tests covering RAM drop, RAM unchanged, skipped/failed process counts, expired proposals, and reused action IDs.
  - `tests/test_web.py` — added test verifying missing nonce, wrong nonce, foreign origin rejection, and happy path proposal gating.
- How to run:
  - Tests: `python -m pytest tests/test_confirmation.py tests/test_web.py -v`
  - Demo: follow steps in `docs/DEMO.md`
- Tests: 188 passed in 4.14s across the full test suite
- Deviations: none
- Open questions: none
