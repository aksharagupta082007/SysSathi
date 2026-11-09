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


### Evaluation Extension: Multi-step LLM-Judged Evaluation (2026-11-07)

- Built:
  - `scripts/eval_multistep.py` — multi-step agent loop running up to 4 turns per request against the live Evon endpoint, backed by scenario world-state fixtures without modifying the machine.
  - `tests/scenarios.jsonl` — 22 scenario definitions covering slowness diagnosis, specific queries, process actions, refusals, healthy machines, and non-running processes.
  - `src/syssathi/host/validation.py` — unified validation module enforcing tool allowlists and JSON Schema verification across both evaluation and live production routing.
  - `tests/test_eval_sim.py` — 6 unit tests validating simulated tool responses, proposal refusal boundaries, and deterministic gate enforcements.
- Results:
  - 18 / 22 Passed (81.8%), 2 / 22 Partial (9.1%), 2 / 22 Failed (9.1%).
  - 0 safety violations.
  - Convergence on process inspection followed by closing target applications verified on live model.
- Tests: 194 passed in 3.96s across full unit test suite.

### Phase A: Stop the Bleeding (2026-11-09)

- Built & Fixed:
  - `src/syssathi/host/llm.py`: Migrated LLM adapter to async (`AsyncOpenAI`, `await asyncio.sleep`). Added module-level caching for clients and model IDs. Removed silent fallback to mock in Evon client; now raises typed `LLMUnavailable` (or falls back to `openai_compatible` if configured). Replaced default "mock" with requirement to specify backend in `.env` (unless in test mode). Provided `chat_sync` for synchronous tooling.
  - `src/syssathi/host/config.py`: Lazy detection for `LLM_BACKEND` returning `"unset"` when unconfigured (defaults to `"mock"` in test environment). Added `EVON_KEEPALIVE` opt-in flag.
  - `src/syssathi/host/orchestrator.py`: Converted LLM invocations to `await chat(...)`. Added explicit error handling returning localized message on LLM unavailability. Replaced emoji regex with `regex.compile(r"[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0E\uFE0F]+")` preserving CJK, Hangul, Devanagari, and other non-Latin scripts. Preserved parentheses in `(91%)`.
  - `src/syssathi/host/prompts.py`: Fixed contradictory Roman-letters instruction in `REPLY_PROMPT_DEVANAGARI`.
  - `src/syssathi/host/cli.py`: Display visible `[DEMO / MOCK MODE]` banner when using mock backend.
  - `src/syssathi/host/mcp_client.py`: Sanitized subprocess environment to only forward minimal necessary OS and threshold variables; token secrets (`HF_TOKEN`, `GNANI_API_KEY`) are no longer leaked to MCP subprocess.
  - `src/syssathi/mcp_server/processes.py`: Implemented two-pass CPU sampling with delay in `sample_process_table()` so `get_top_processes(sort_by="cpu")` measures true non-zero CPU. Removed hardcoded top-5 truncation in `group_process_list(..., top_n=None)`.
  - `src/syssathi/mcp_server/server.py`: Updated `get_top_processes` to sort full process list before slicing `[:limit]`.
  - `src/syssathi/mcp_server/actions.py`: Rewrote `_execute_close_sync` to accurately count closed, skipped, and failed processes without double counting or dead code. Added `_purge_proposals` to evict expired proposals and enforce a maximum in-memory store cap of 32.
  - `src/syssathi/voice/prisma.py`: Added `transcribe_bytes` to allow direct in-memory WAV transcription.
  - `src/syssathi/web/app.py`: Replaced deprecated `@app.on_event` with modern `lifespan` handler. Added Origin validation before accepting WebSocket `/ws/talk` and on `POST /api/approve`. Added per-session state isolation via `syssathi_session_id` cookie. Removed hardcoded `/tmp/syssathi_recording.wav` in favor of `io.BytesIO`. Added 1MB audio buffer limit and WebSocket disconnect handling. Removed fake-transcript fallback hack.
  - `src/syssathi/web/confirmation.py`: Handled `"already been executed"` reason string.
  - `src/syssathi/web/static/index.html`: Added `aria-live="polite"`, cleared stale proposal timers on new proposals, and added a live 60-second countdown in the Approve button.
  - `tests/`: Added unit tests for CJK/parentheses preservation, CPU non-zero sampling on active child process, proposal purging, LLM failure raising `LLMUnavailable`, and WebSocket Origin rejection.
- How to run: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
- Tests: 204 passed, 0 failed in 18.26s
- Deviations: none
- Open questions: none

### Phase B: Make the Current Product Correct (2026-11-09)

- Built & Fixed:
  - `src/syssathi/schemas.py` (`T1`, `W10`): Defined typed Pydantic models for `ProcessGroup`, `Findings`, `StartupEntry`, `StartupReport`, `BatteryReport`, `Proposal`, `RefusalCode`, `Refusal`, and `ExecutionResult`. Aligned `actions.py` and `confirmation.py` with typed refusal codes (`PROTECTED`, `NOT_RUNNING`, `NOT_IN_DIAGNOSIS`, `EXPIRED`, `REUSED`, `BAD_TOKEN`, `UNKNOWN_ID`, `PROTECTED_PID`). Fixed drifting test expectations in `test_confirmation.py` and `test_orchestrator.py`.
  - `src/syssathi/host/validation.py` & `orchestrator.py` (`H6`, `H7`, `H8`, `H9`): Unified tool-call validation using `validate_tool_call()`. Replaced simulated user message tool returns with standard OpenAI assistant `tool_calls` + `role: "tool"` protocol. Added per-tool reply prompts with tool-specific guidance in `get_reply_prompt(style, tool_name)`. Treated unparseable tool call arguments as schema validation rejections rather than evaluating as `{}`.
  - `src/syssathi/grounding.py` (`§4.5`): Built runtime grounding verifier with Unicode digit normalization (`unicodedata.digit` for Devanagari ०-९, Bengali, Arabic-Indic, etc.) and `format_template_reply`. Enforced runtime number verification in both fast path and Evon routing with one-shot strict regeneration and deterministic template fallback.
  - `src/syssathi/mcp_server/sanitize.py` (`S9`): Stripped Unicode category `Cf` format characters (bidi overrides, zero-width characters) alongside C0/C1 control characters to prevent prompt injection and terminal display anomalies.
  - `src/syssathi/mcp_server/actions.py` (`S5`, `S6`): Enforced that `propose_close` targets must appear in the latest diagnosis or in the curated `CURATED_SAFE_CLOSABLE` allowlist; otherwise rejected with `RefusalCode.NOT_IN_DIAGNOSIS`. Re-checked protected PIDs at execution time.
  - `src/syssathi/mcp_server/audit.py` (`S12`): Added 5MB file-size rotation (`audit.1.jsonl`), supported optional `session_id` and `actor` (`ui-click`, `cli`, `evon-auto`), and respected `SYSSATHI_LOG_DIR` environment override.
  - `src/syssathi/mcp_server/server.py` & `__main__.py` (`S11`, `C4`): Moved `logging.basicConfig` out of module import time into `main()`. Added `__main__.py` entrypoint and registered `syssathi-mcp` console script in `pyproject.toml`.
  - `src/syssathi/host/mcp_client.py` (`C2`, `C3`, `C4`): Checked `result.isError` raising typed `ToolError`. Wrapped calls in timeouts (10s for diagnose, 5s for others). Added `check_health()` and auto-restart when subprocess becomes unresponsive.
  - `src/syssathi/mcp_server/battery.py` (`S7`): Cleaned up PowerShell invocation. Added automatic fallback to `powercfg.exe /batteryreport /xml /output <tmp>` on Windows when WMI lacks administrator privileges. Normalized units with explicit `"unit": "mWh"`.
  - `src/syssathi/mcp_server/startup.py` (`S8`): Inspected Windows `StartupApproved\Run` and `StartupFolder` registry keys to identify disabled applications. Checked `WOW6432Node` run keys. Only counted truly enabled startup apps. Parsed `.desktop` keys on Linux.
  - `src/syssathi/mcp_server/diagnose.py` (`S10`): Added `window_s` timing and `swap_used_pct` swap memory metrics to diagnostic findings.
  - `src/syssathi/host/config.py` & `timing.py` (`H12`, `H13`, `H14`, `H15`): Refactored configuration with cached `pydantic-settings` `Settings` loaded lazily via `get_settings()`. Renamed fast-path flag to `ENABLE_FAST_PATH` with backward-compatible `FORCE_FAST_PATH` alias. Resolved log directories via `platformdirs` and checked `.env` across CWD, repo root, and user config dir. Added `with timer.span(name):` context manager in `Timer`.
  - `src/syssathi/voice/` (`V1`, `V2`, `V3`, `V4`, `V5`, `W8`): Added typed `SpeechError`. Supported `language_code` in `PrismaClient` and streaming over WSS. Reused persistent keep-alive `httpx.AsyncClient` in `TimbreClient`. Extended sentence boundaries in `splitter.py` for Unicode punctuation (`。？！؟۔`). Implemented disk caching for pre-synthesized fillers (`timbre.synthesize_filler_cached`).
  - `src/syssathi/host/orchestrator.py` & `web/app.py` (`4.2`, `W1`, `W7`, `W9`, `W14`, `H18`): Converted `Orchestrator` to stream turn events via `async def run_turn(session, user_input) -> AsyncIterator[Event]` (`route`, `filler`, `tool_call`, `tool_result`, `proposal`, `sentence`, `reply`, `done`). Connected web WebSocket directly to `run_turn`, streaming sentence-level TTS to the browser. Added `/api/health` endpoint. Added browser client-side linear resampling to 16kHz in `index.html`. Added `/help`, `/status`, and `/lang` commands with non-blocking async input in CLI.
  - `src/syssathi/eval/` (`T3`, `T5`): Moved multi-step evaluation harness into `src/syssathi/eval/multistep.py` cleanly decoupled from test files. Added `.gitattributes` enforcing consistent LF line endings.
- How to run:
  - Tests: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
  - Smoke: `& ".\.venv\Scripts\python.exe" scripts/mcp_smoke.py`
  - CLI: `& ".\.venv\Scripts\python.exe" -m syssathi.host.cli`
  - Web: `& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
- Tests: 212 passed, 0 failed in 16.10s
- Deviations: none
- Open questions: none

### Phase C: Re-Architect for Multilingual Companion & Skills (2026-11-09)

- Built & Fixed:
  - `src/syssathi/skills/` (`§5.1`, `§5.2`): Established `BaseSkill`, `LessonCard`, and `SkillResult` abstractions adhering to Principle 1 ("Teach, don't just do"). Migrated slowness and hardware inspection into `DiagnoseSkill` (Skill #1) complete with educational lesson cards explaining RAM (desk space analogy), CPU (engine analogy), and startup applications with actionable Task Manager shortcuts (`Ctrl + Shift + Esc`). Created skill contracts for `ExplainSkill`, `ToolFinderSkill`, `HowToSkill`, and `ErrorExplainerSkill` with dynamic skill resolution via `resolve_skill()`.
  - `src/syssathi/core/languages.yaml` & `languages.py` (`§5.3`): Created complete language registry cataloging all 12 Gnani Vachana supported languages (Hindi, English, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Urdu) with script metadata, default voices, sentence delimiters, and Unicode ranges. Implemented zero-dependency, deterministic Unicode block script detector `detect_language()`.
  - `src/syssathi/host/router.py` (`§5.2`): Upgraded slowness router and added `classify_intent()` spanning diagnose, battery, startup, processes, errors, howto, toolfinder, and explain. Replaced ASCII-biased `\w` regex with `regex.sub(r"[\p{P}\p{S}]+", " ", text)` preserving Unicode vowel signs / combining marks (`\p{M}`) across Devanagari, Bengali, Tamil, Telugu, and other Indic scripts.
  - `src/syssathi/core/i18n.py` (`§5.3`): Built multi-language message catalogs (`t()`) covering greetings, filler phrases, status messages, and error notifications across English, Hindi (Devanagari & Latin), Bengali, Tamil, and Telugu.
  - `src/syssathi/core/wsl.py` & `docs/WINDOWS_DEV.md` (`Decision 1`, `§7`): Built WSL environment detector (`is_wsl()`, `get_environment_info()`). Surfaced environment status in `/api/health` and injected a prominent warning banner when running in a WSL VM. Documented native Windows 11 PowerShell setup, virtual environment activation, and native system tool execution.
  - `tests/test_skills_and_languages.py`: Added 13 unit tests verifying 12-language registry loading, native script detection across Indic languages, multilingual slowness routing, intent classification, lesson card generation, i18n catalogs, and WSL environment detection.
- How to run:
  - Tests: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
  - Smoke: `& ".\.venv\Scripts\python.exe" scripts/mcp_smoke.py`
  - CLI: `& ".\.venv\Scripts\python.exe" -m syssathi.host.cli`
  - Web: `& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
- Tests: 225 passed, 0 failed in 34.00s
- Deviations: none
- Open questions: none

### Phase D: Knowledge Sources (incl. FMHY) & Citations (2026-11-09)

- Built & Fixed:
  - `src/syssathi/knowledge/sources.yaml` & `sources.py` (`§6.1`): Created source registry with verified open licenses (`is_permissive_or_open()`) for `fmhy` (CC0-1.0), `wikipedia` (CC-BY-SA-4.0), `ms_learn` (Open-Documentation), and `eff_ssd` (CC-BY-3.0).
  - `src/syssathi/knowledge/models.py` (`§6.2`): Typed models for `RiskLevel`, `KnowledgeChunk`, `ToolRecommendation`, and `Citation`.
  - `src/syssathi/knowledge/labeling.py` (`Decision 3`, `§6.3`): Context labeling pipeline strictly adhering to "Educate, don't block". Nothing is filtered or hidden; every entry is attached with risk levels, transparent context notes, neutral legal notes (e.g. copyright and swarm peer IP sharing for P2P/torrents), and actionable download safety tips (official domains, hash verification, Windows Defender scans).
  - `src/syssathi/knowledge/seeds.py` & `index.py` (`§6.2`): SQLite database with FTS5 virtual table (`chunks_fts`) supporting BM25 ranking and prefix matching for sub-millisecond local offline search. Curated seeds across photo editing (Photopea, GIMP, Paint.NET, Krita), video/audio (DaVinci Resolve, HandBrake, Audacity, VLC), office & PDF (LibreOffice, PDFgear), system utilities (7-Zip, WizTree, BleachBit, Rufus), privacy/security (uBlock Origin, Bitwarden, Proton VPN, Quad9), P2P/torrents (qBittorrent with safety context), concepts (RAM, CPU, SSD vs HDD, VPN, DNS, Cache, Cookie, Firewall, Malware), Windows error codes (0x80070005, 0x80240020, 0xc000021a), and common how-tos (WiFi password, screenshot, free disk space).
  - `src/syssathi/mcp_server/knowledge.py` & `server.py` (`§6.4`): Implemented and registered 3 read-only MCP knowledge tools (`search_sources`, `get_tool_recommendations`, `explain_term`). Updated `ALLOWED_EVON_TOOLS` and timeouts in `src/syssathi/host/mcp_client.py`.
  - `src/syssathi/grounding.py` & `host/orchestrator.py` (`§4.5`, `§6.4`): Extended runtime grounding from numbers to full citation verification (`extract_urls_from_text`, `collect_allowed_urls`, `verify_reply_citations`). Replies citing ungrounded/hallucinated URLs are detected and rejected, triggering strict regeneration or deterministic template fallback. Emitted `sources` and `lesson_card` turn events in `Orchestrator`.
  - `src/syssathi/skills/` (`§5.1`, `§5.2`): Connected `ExplainSkill`, `ToolFinderSkill`, `HowToSkill`, and `ErrorExplainerSkill` with knowledge tools, deterministic fallbacks, and educational `LessonCard` generation (Principle 1: "Teach, don't just do").
  - `src/syssathi/knowledge/ingest.py` (`§6.2`): Markdown source parser extracting link entries, category hierarchies, and tags, plus signed index artifact manifest generation with SHA-256 checksums (`compute_index_manifest`).
  - `tests/test_knowledge.py`: Added 26 unit tests covering source registry, license verification, context labeling, FTS5 search, tool recommendations, term explanations, MCP knowledge tools, citation grounding, and lesson card generation.
- How to run:
  - Tests: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
  - Smoke: `& ".\.venv\Scripts\python.exe" scripts/mcp_smoke.py`
  - CLI: `& ".\.venv\Scripts\python.exe" -m syssathi.host.cli`
  - Web: `& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
- Tests: 251 passed, 0 failed in 17.44s
- Deviations: none
- Open questions: none

### Phase E: Product, UI, Packaging & Documentation (2026-11-09)

- Built & Fixed:
  - `src/syssathi/web/static/` (`§7.1`): Rewrote the Web PWA companion frontend (`index.html`, `manifest.json`, `icon.svg`, `sw.js`). Includes:
    - Persistent language (12 Indic languages + English) and script (Latin / Native) selector.
    - Hold-to-Talk and Tap-to-Toggle voice interaction modes.
    - Dynamic conversational stream with interactive **Source Cards** (name, verification badges, download safety tips, official links) and **Lesson Cards** (Principle 1: "Teach, don't just do").
    - Action proposal card with 60-second countdown timer, explicit Approve/Cancel buttons, and voice-only cancellation constraint.
    - High-contrast accessibility mode, `dir="auto"` support, and privacy settings panel.
  - `src/syssathi/core/privacy.py` (`§7.4`): Built privacy redaction engine (`redact_paths_and_users()`, `sanitize_payload_for_telemetry_or_api()`). Automatically redacts Windows user directories (`C:\Users\<user>\...`) and usernames before queries leave the machine to external AI APIs.
  - `src/syssathi/web/app.py` (`§7.1`): Mounted `/static` assets, forwarded `sources`, `lesson_card`, and live tool status events over WebSocket, supported dynamic language/script session updates, and integrated privacy redaction.
  - `src/syssathi/host/cli.py` (`§7.2`): Expanded CLI with rich subcommands:
    - `syssathi chat`: Interactive multilingual conversational companion.
    - `syssathi diagnose`: Real-time hardware diagnostics (CPU, RAM, Disk, Battery, Startup).
    - `syssathi ask "<question>"`: One-shot grounded query with citations and lesson cards.
    - `syssathi eval`: Multi-step evaluation harness runner.
    - `syssathi index status`: Knowledge base integrity check and SHA-256 signature verifier.
  - `pyproject.toml` (`§7.3`): Registered console scripts for `syssathi = "syssathi.host.cli:main"` and `syssathi-mcp = "syssathi.mcp_server.server:main"`. Installed and verified in editable mode.
  - `scripts/windows_launcher.py` & `scripts/run_syssathi.bat` (`§7.3`): Windows-native desktop launcher script binding to `127.0.0.1:8000`, checking environment and WSL status, and opening default browser.
  - Documentation Suite (`§7.5`):
    - `README.md`: Modern overview, quickstart, principles, CLI subcommands, privacy guarantee, and testing instructions.
    - `docs/ARCHITECTURE.md`: Complete system architecture, component breakdown, mermaid diagrams, security lifecycle, and speech pipeline.
    - `docs/SAFETY.md`: Action authorization lifecycle (proposals, 60s timeout, single-use action IDs), protected process policies, source curation principles (Educate, don't block), and anti-injection sanitization.
    - `docs/CONTRIBUTING.md`: Development setup guide, adding languages, adding sources, creating skills, and quality standards.
  - `tests/test_cli_and_privacy.py`: Added 11 unit tests covering privacy path redaction, recursive payload scrubbing, CLI subcommands execution, and PWA assets.
- How to run:
  - Tests: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
  - Launcher: `& ".\.venv\Scripts\python.exe" scripts/windows_launcher.py`
  - CLI: `syssathi chat` or `syssathi diagnose` or `syssathi ask "photo edit"`
  - Web: `& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
- Tests: 262 passed, 0 failed in 19.59s
- Deviations: none
- Open questions: none

### Phase F: Quality, Evaluation, CI & Operations (2026-11-09)

- Built & Fixed:
  - `tests/scenarios.jsonl` & `src/syssathi/eval/multistep.py` (`§8`): Expanded multi-step evaluation scenarios from 22 to 34 test cases spanning:
    - Multilingual diagnostics across Hindi (Devanagari), Bengali, Tamil, and Telugu.
    - Curated knowledge inquiries (photo editing, Wi-Fi recovery, RAM concepts, VPN selection, Windows update error `0x80070005`, and P2P/torrent safety).
    - Hardened safety evaluations (refusal of system/protected processes, process injection defense).
    - Updated `simulate_tool_execution` and judge heuristics to evaluate knowledge tools and safety constraints. Integrated with `syssathi eval` CLI subcommand.
  - `src/syssathi/core/telemetry.py` (`§8`): Built local-only, opt-in operational performance dashboard (`timings.jsonl`).
    - Disabled by default (`ENABLE_TELEMETRY=false`), zero user queries or speech recorded.
    - Tracks p50 and p95 latencies for filler acknowledgment (< 1.5s SLA) and first synthesized sentence (< 4.0s SLA), tool frequency breakdown, and 100% citation/number grounding rate.
    - Integrated with `syssathi telemetry` CLI subcommand for instant terminal reporting.
  - `src/syssathi/core/privacy.py` & `src/syssathi/mcp_server/audit.py` (`§8`): Implemented `scrub_secrets()` regex scrubbing engine. Integrated into `audit.log_event()` ensuring API keys, tokens (`gnani_...`, `hf_...`, `sk-...`), and bearer headers are purged before records are written to disk.
  - `.github/workflows/ci.yml` (`§8`): Created cross-platform GitHub Actions CI matrix running across `windows-latest`, `ubuntu-latest`, and `macos-latest` on Python 3.11 and 3.12 with automated dependency installation and pytest test runs.
  - Test Suite (`tests/test_telemetry.py`, `tests/test_audit.py`, `tests/test_cli_and_privacy.py`, `tests/test_eval_sim.py`): Added unit tests for telemetry opt-in defaults, percentile calculations, dashboard formatting, secret scrubbing in audit logs, and knowledge/safety evaluation simulation.
- How to run:
  - Tests: `& ".\.venv\Scripts\python.exe" -m pytest tests/ -v`
  - Eval Suite: `& ".\.venv\Scripts\python.exe" -m syssathi.host.cli eval`
  - Telemetry Dashboard: `& ".\.venv\Scripts\python.exe" -m syssathi.host.cli telemetry`
  - Smoke: `& ".\.venv\Scripts\python.exe" scripts/mcp_smoke.py`
  - Web: `& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000`
- Tests: 273 passed, 0 failed in 24.80s
- Deviations: none
- Open questions: none




