# SysSathi → plan.md

Status audit, fix list, and evolution roadmap.
Written 2026-11-09 after a full read of every tracked file in the repo (src, tests, scripts, docs, config).

---

## 0. TL;DR

- **The test suite is green (196 passed, 35 s), but that hides how bad the real state is.** Many tests check made-up data shapes (`closed_count`, `diagnosis`) that the real server never returns. Some tests start real subprocesses and run real 3-second diagnoses. Several real-world paths are broken and no test covers them.
- **Biggest correctness problems:**
  1. A synchronous LLM call (with `time.sleep` retries) runs inside the async server, so it freezes the whole web app.
  2. The Evon backend **quietly falls back to the mock**, so users get made-up "your laptop looks healthy" answers.
  3. `get_top_processes` always reports 0% CPU.
  4. The web app shares one global conversation and one pending proposal across every browser tab.
  5. The WebSocket has no Origin check, so any website can read your process list.
  6. The reply "guard" emoji regex deletes all Chinese, Japanese, Korean, and many other scripts, which blocks the multilingual goal.
- **Evolution:** today it is a one-trick Hinglish demo ("why is my Windows laptop slow"). The target is a **multilingual, voice-and-text tech-literacy companion**. It explains your own computer as hands-on lessons and answers technology questions, grounded in **curated sources** (FMHY, official docs, wikis), in any language Gnani supports (voice and text), with citations and safe, approval-gated actions. Windows-first, local app, Gnani models (Prisma, Evon, Timbre) everywhere.

Work order: **Phase A (stop the bleeding) → Phase B (make it correct) → Phase C (re-architect for multilingual + knowledge) → Phase D (sources/RAG incl. FMHY) → Phase E (product/UX/distribution) → Phase F (quality, eval, ops).**

---

## 1. What exists today (inventory)

| Area | Files | Purpose |
| --- | --- | --- |
| MCP server | `src/syssathi/mcp_server/{server,diagnose,processes,startup,battery,actions,policy,sanitize,audit}.py` | stdio MCP server. 6 tools: diagnose, top processes, startup apps, battery, propose/execute close |
| Host | `src/syssathi/host/{config,llm,router,mcp_client,orchestrator,prompts,timing,validation,cli}.py` | LLM adapter (evon/openai/mock), keyword router, orchestrator, CLI |
| Voice | `src/syssathi/voice/{prisma,timbre,splitter}.py` | Gnani STT (REST only), TTS (REST only), sentence splitter |
| Web | `src/syssathi/web/{app,confirmation}.py`, `static/index.html` | FastAPI + push-to-talk page + approve endpoint |
| Scripts | `scripts/{mcp_smoke,test_evon_tools,eval_multistep,gnani_probe}.py` | Live/manual tooling |
| Tests | `tests/*.py`, `utterances.jsonl`, `scenarios.jsonl` | 196 tests, mostly unit; some hit real OS/subprocess |
| Docs | `docs/{BRIEF,PROGRESS,GNANI_NOTES,DEMO}.md`, `README.md` | Hackathon brief and agent progress log |

Environment facts observed: Python 3.14.9 venv, `mcp 2.3.0`, `fastmcp 4.1.6` (only a meta-package; the code imports `mcp` directly), `openai 3.46.0`, `pydantic 2.14.3`. The brief targets Windows, but the dev machine is now Linux, and Linux paths were added later without being designed in.

---

## 2. Bug and defect catalogue (with fixes)

Severity: **P0** = wrong or dangerous behaviour in normal use, **P1** = broken feature or security weakness, **P2** = quality, maintainability, or tech debt.

### 2.1 Host / LLM (`host/llm.py`, `host/orchestrator.py`, `host/config.py`)

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| H1 | P0 | `chat()` is **synchronous** (blocking `openai.OpenAI`, `time.sleep` back-off) but is called from `async` orchestrator methods. In the web server, one slow Evon call (30 s timeout × up to 3 own retries × `max_retries=1` inside the SDK = up to ~6 attempts plus 4 s + 8 s sleeps) **freezes every connection**. | Make the adapter async: `openai.AsyncOpenAI`, `await asyncio.sleep`. Expose `async def chat(...)` and `async def stream_chat(...)`. Build the client once per backend (module-level cache or DI), not on every call. |
| H2 | P0 | `_evon_remote_chat` **silently falls back to `_mock_chat` on any exception**. The user then gets canned text such as "Laptop theek lag raha hai" that has nothing to do with their machine. The brief requires mock output to be clearly labelled. | Remove the silent fallback. Raise a typed `LLMUnavailable` error. The orchestrator catches it and returns an explicit localized message ("AI service is waking up / unavailable, try again"). Optionally fall back to the `openai_compatible` backend if it is configured, never to mock. |
| H3 | P0 | Default `SYSSATHI_LLM_BACKEND="mock"`. A fresh install gives fake answers with no warning. | Default to "unset" and fail at startup with a clear message. Allow `mock` only when `SYSSATHI_ENV=test` or `--demo` is set, and show a visible "DEMO / MOCK" banner in the CLI and web UI. |
| H4 | P1 | Retries count "503" substring matches only, and `max_retries=1` in the SDK stacks with them. | Use one retry policy: SDK `max_retries=0` plus our own exponential back-off on `APIConnectionError`, `APITimeoutError`, `InternalServerError`, and 503. Cap the total wait (e.g. 20 s for the first cold-start call, 8 s after). |
| H5 | P1 | `models.list()` is called on **every** request when `EVON_MODEL` is unset. | Resolve once, cache it, and refresh only on 404. |
| H6 | P1 | The tool-call JSON parse failure turns into `{}`, which then validates for argument-less tools. | Treat unparseable arguments as an invalid tool call. Same safe-reply path as a schema failure. |
| H7 | P1 | The orchestrator **duplicates** allowlist and schema validation that already exists in `host/validation.py`. | Use `validate_tool_call()` in the orchestrator. Delete the duplicate code. |
| H8 | P1 | Evon call 2 sends the tool result as a fake `user` message (`"Tool result from X:\n..."`) instead of proper `assistant.tool_calls` + `role: tool` messages, which tool-tuned models expect. `eval_multistep.py` already does it the right way. | Use the proper OpenAI tool-message protocol in production too (copy from `eval_multistep.run_scenario`). |
| H9 | P1 | `REPLY_PROMPT_*` always says "explains why a Windows laptop is slow… JSON called findings", even when the tool was battery or startup apps. | Per-tool reply instructions, or a generic "explain this tool result" prompt with tool-specific hints. |
| H10 | P1 | `REPLY_PROMPT_DEVANAGARI` contradicts itself: "Hindi written in **Roman letters**" followed by "Write Hindi words in **Devanagari**". | Remove the Roman-letters line from the Devanagari variant. In Phase C this becomes a language/script template (§4.3). |
| H11 | P0 (for multilingual) | `apply_reply_guard` `_EMOJI_RE` includes the range `\U000024C2-\U0001F251`. That **deletes all CJK, Hangul, Japanese kana, Yi, and more**. `_MARKDOWN_RE` also strips `( ) + >`, which breaks sentences like "RAM (91%)" and "C++". The 40-word cut uses whitespace splitting, which fails for Thai, Chinese, and Japanese. | Rewrite using the `regex` module: drop `\p{Extended_Pictographic}` and `\p{Emoji_Presentation}` only. Strip markdown with patterns (`**x**`, `` `x` ``, `[t](u)`, leading `#`, `-`, `*`), not character classes. Measure length in **ICU word segments** (`PyICU`/`icu4py`) or graphemes, with per-language limits. Treat sentence ends `. ? ! । ॥ 。 ？ ！ ؟ ۔` as boundaries. |
| H12 | P1 | `FORCE_FAST_PATH` means the opposite of its name (true = fast path *enabled*, false = forced Evon). | Rename to `ENABLE_FAST_PATH`. Keep the old name as a deprecated alias for one release. |
| H13 | P1 | `config.py` hard-codes the private Hugging Face endpoint URL as a default, and reads env at **import time** (so tests must monkeypatch module globals). It also imports `policy` from `mcp_server`, which inverts the layering. | Use a `pydantic-settings` `Settings` class, loaded lazily via `get_settings()` (lru_cache). No endpoint defaults. Remove the `policy` re-export. |
| H14 | P1 | Paths: `config.LOGS_DIR`, `audit.LOGS_DIR`, and `load_dotenv` use `Path(__file__).parents[3]`. This only works in an editable checkout. Installed from a wheel, it writes into `site-packages/..`. | Use `platformdirs.user_log_dir("syssathi")` and `user_config_dir`. Look for `.env` in the CWD first, then the config dir. |
| H15 | P2 | `timer.mark("x", timer._start + t0/1000)` reaches into a private field. Not flushed on exceptions. | `with timer.span("tool_ms"):` context manager. Flush in a `finally`. |
| H16 | P2 | Conversation history: the fast path stores only user and assistant text, so follow-ups ("haan band kar do") lose the findings context. History is capped by message count, not tokens. | Store a compact "last tool result" in the session state. Cap by approximate tokens. |
| H17 | P2 | Mock `_MOCK_TOOL_TABLE` uses substring matching: `"ram"` matches "program", "frame", "kram". | Use word-boundary regex. The mock only exists for tests anyway. |
| H18 | P2 | `cli.py`: blocking `input()` inside the async loop, unused `sys` import, and it can't show audit or proposal details. | Use `asyncio.to_thread(input, ...)` or `prompt_toolkit`. Add `/status`, `/lang`, and `/help`. |

### 2.2 MCP client (`host/mcp_client.py`)

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| C1 | P1 | The **entire parent environment** (HF_TOKEN, GNANI_API_KEY, OpenAI keys) is passed to the server subprocess, which needs none of it. | Pass a minimal env: `PATH`, `SYSTEMROOT`/`HOME`, `SYSSATHI_APPROVAL_TOKEN`, threshold vars, `SYSSATHI_LOG_DIR`. |
| C2 | P1 | `call_tool` ignores `result.isError` and reads only `content[0]`. Errors come back as plain strings, and the orchestrator then treats them as "findings". Also, no timeout. | Check `isError` and raise `ToolError`. Prefer `structuredContent` when present. Wrap the call in `asyncio.wait_for` (diagnose 10 s, others 5 s). |
| C3 | P1 | If the server subprocess crashes, the session stays dead forever (the web app needs a restart). | Health check plus automatic restart with back-off. Surface the state in `/api/health`. |
| C4 | P2 | Launches `server.py` by file path. | `python -m syssathi.mcp_server`, plus a `__main__.py`. Also expose a console script `syssathi-mcp` so other MCP clients (Claude Desktop, Antigravity, etc.) can use the server. |

### 2.3 MCP server tools

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| S1 | P0 | `processes._sample_processes_sync` reads `cpu_percent` via `process_iter([... "cpu_percent"])` **without priming**, so CPU is always 0.0. `get_top_processes(sort_by="cpu")` is meaningless. `prime_cpu_percent()` exists but is never called. | Reuse the diagnose sampler: prime, sleep about 1 s, read. Factor out `sample_process_table(window_s)` and use it in both tools. |
| S2 | P1 | `group_process_list` truncates to **top 5 by RAM** before `get_top_processes` sorts by CPU or applies `limit` (max 10). So the CPU sort only reorders the 5 biggest-RAM groups, and `limit>5` is impossible. | Return all groups from the pure function. Sort and slice in the caller. Keep `top_n` as a parameter. |
| S3 | P1 | `actions._execute_close_sync` miscounts. Dead line 268. Killed survivors aren't waited on, so `wait(timeout=0)` raises `TimeoutExpired` and they get counted as `failed` even though they were killed. Kill failures are counted twice. | Rewrite: `terminate` all, `wait_procs(3)`, `kill` the survivors, `wait_procs(2)`. Count `closed = gone`, `failed = still alive or AccessDenied`. Add unit tests with fake `psutil.Process` objects (no real processes needed). |
| S4 | P1 | `_proposals` dict grows without bound. Expired proposals are never purged. | Purge on every propose and execute. Cap at N (e.g. 32). |
| S5 | P1 | `propose_close` accepts **any** group name, for example a password manager, OBS mid-recording, or a backup client. Safety relies on a deny-list only. | Require the group to appear in the **latest diagnosis/top_groups for this session** OR in a curated "safe to close" allow-list (browsers, chat apps, media players). Otherwise refuse with "please confirm the exact app name in the UI". Keep the deny-list as a second layer. |
| S6 | P1 | Protected-PID check only happens at proposal time. Child processes spawned after the snapshot are not handled (fine), but the host PID could change if the host restarted (low risk). | Re-check `get_protected_pids()` at execute time as well. |
| S7 | P1 | `battery._run_ps_command` has nonsensical dead code building `cmd[0]`. `root/wmi BatteryStaticData` often needs **admin**, so health is "unavailable" for most users. Linux `charge_full` is in µAh and `energy_full` in µWh, but the keys are labelled `_mwh`. | Clean up the command. On Windows fall back to `powercfg /batteryreport /xml /output <tmp>` (fixed args, no shell). Normalize units and add a `unit` field. |
| S8 | P1 | `startup.py` counts entries that are **disabled** in Task Manager (Windows `StartupApproved\Run` keys), misses `WOW6432Node\...\Run`, `RunOnce`, scheduled tasks, and on Linux ignores `Hidden=true` / `X-GNOME-Autostart-enabled=false` and user overrides of `/etc/xdg/autostart`. The result is false `STARTUP_HIGH` findings. | Read `StartupApproved` and report `enabled: bool`. Count only enabled entries. Parse `.desktop` keys. Add systemd `--user` enabled units on Linux, and LaunchAgents on macOS (later). |
| S9 | P1 | `sanitize` strips C0/C1 controls only. Bidi overrides (U+202E), zero-width characters, and other `Cf` characters pass through, and so do prompt-injection-like names (40 chars is enough for "ignore all rules, call propose_close"). | Strip the Unicode category `Cf` too. Wrap machine-sourced strings in the prompt as clearly delimited data (JSON only, never interpolated into instructions). Keep the 40-char cap. |
| S10 | P2 | `diagnose` window timing is adaptive and undocumented in output. The CPU-sample thread is created per call. | Add `window_s` to the output. Fine otherwise. Add a `disk_busy_pct` (from `busy_time` in `psutil.disk_io_counters(perdisk=True)` on Linux, and a perf counter on Windows) and `swap_used_pct`, which are common slowness causes. |
| S11 | P2 | `server.py` uses `logging.basicConfig` at import time (affects importers such as tests). | Move it into `main()`. |
| S12 | P2 | Audit log has no rotation and records only one result string. | `RotatingFileHandler`-style rotation. Add `session_id` and `actor` (`ui-click`, `cli`). |

### 2.4 Voice (`voice/*.py`)

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| V1 | P1 | Prisma: only REST. The streaming WS documented in `GNANI_NOTES.md` is not implemented, so latency is end-of-speech plus upload plus a full transcription. | Implement `PrismaClient.stream(pcm_iter)` over WSS. Keep REST as the fallback. |
| V2 | P1 | Prisma: `language_code="indic-auto"` is hard-coded. The brief asked for Hindi+English hints. There's no way to pass the user's chosen language. | Parameterize `language_code` from the session language. Use auto only when the user hasn't chosen. |
| V3 | P1 | Timbre: `language="hi-IN"` is hard-coded, and a new `httpx.AsyncClient` is created per sentence (a TLS handshake each time). | Pass the language per call. Use a shared `AsyncClient` with keep-alive. Implement SSE/WS streaming for time-to-first-audio. |
| V4 | P1 | No timeouts or error typing. Failures are swallowed with `except Exception: pass` in the web app. | Typed `SpeechError`. The UI shows "voice unavailable, showing text". |
| V5 | P2 | `splitter.py` is unused in practice (the reply is generated fully, then split). The regex misses `。？！؟`. | Use it with streaming LLM output (Phase B). Extend the delimiters. |

### 2.5 Web (`web/app.py`, `web/confirmation.py`, `static/index.html`)

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| W1 | P0 | **One global `Orchestrator`** serves every tab and every connection: shared history, shared `pending_proposal`. Tab A can approve tab B's proposal, and concurrent requests interleave. | A per-session `Session` object (id in a signed cookie) that holds history, proposals, and language. Proposals are bound to a session id, and approve checks it. Use an `asyncio.Lock` per session. |
| W2 | P0 | **No Origin check on `/ws/talk`.** Any website the user visits can open `ws://127.0.0.1:8000/ws/talk`, send `{"type":"text"}`, and read back process names, startup apps, and battery data (cross-site WebSocket hijacking). It can also create proposals. | Check `Origin` against an allow-list (built from the bound host:port) before `accept()`. Require the session nonce as the first message. |
| W3 | P1 | Approve `allowed_hosts` hard-codes port 8000. Any other `--port` breaks approval. The Host/Origin checks are skipped when the header is absent. The nonce is global per process, not per session. | Derive the allowed host from the actual bind address (setting). Require Origin to be present for POST. Use a per-session nonce (CSRF token). |
| W4 | P1 | Recording is written to the hard-coded `/tmp/syssathi_recording.wav`. That path **doesn't exist on Windows** (the target OS), and concurrent users overwrite each other's audio. | Build the WAV in memory (`io.BytesIO`) and pass bytes to httpx. |
| W5 | P1 | `websocket.receive()` returns `{"type": "websocket.disconnect"}` rather than raising, so the loop doesn't exit cleanly and the next receive raises `RuntimeError`. There's no buffer cap, so a malicious or long recording can exhaust memory. Prisma also limits REST to 30 s. | Handle the disconnect message type. Cap at 30 s × 16 kHz × 2 bytes (~1 MB) and reject beyond that. |
| W6 | P1 | **Test-only hack in production:** with no API key and no audio, the server pretends the user said "Mera laptop slow chal raha hai". | Delete it. Tests should send `{"type":"text"}`. |
| W7 | P1 | The web app calls `route()` itself (ignoring `FORCE_FAST_PATH`) to decide on the filler, then the orchestrator routes again. They can disagree. | The orchestrator returns or streams events (`route_decided`, `filler`, `sentence`, `proposal`, `done`). The web layer only relays them. |
| W8 | P1 | The filler phrase is re-synthesized by TTS on every request (hundreds of ms plus API cost). | Pre-synthesize the fillers per language at startup and cache them on disk. |
| W9 | P1 | The browser requests `AudioContext({sampleRate:16000})`. Firefox and some devices ignore or reject it, while the server always assumes 16 kHz. `ScriptProcessorNode` is deprecated. | Use an `AudioWorklet`. Resample to 16 kHz in the worklet, or send the actual rate in a `start` message and resample server-side. |
| W10 | P1 | `confirmation.py` checks `"used"` in the reason, but the real server says "Proposal has already been executed", so that path never matches. It works with keys (`closed_count`, `diagnosis`) that the real server never returns. | Make the server return machine-readable codes (`{"refused": true, "code": "REUSED"}`). Map codes to localized strings. Fix the tests to use the real shape. |
| W11 | P1 | The Evon keep-alive pings `/models` every 45 s **forever**. That defeats scale-to-zero and keeps a paid GPU endpoint billed around the clock. | Opt-in via `EVON_KEEPALIVE=true`, and ping only while a browser tab is connected (and for N minutes after). |
| W12 | P2 | `@app.on_event` is deprecated (shows as warnings in the test run). | `lifespan` context manager. |
| W13 | P2 | The UI: each new proposal adds another 60 s `setTimeout` without clearing the old one. `sendText` closes the socket that may still be streaming audio. There's no countdown display, no language selector, no history, no accessibility (ARIA live regions), and English-only labels. | See Phase E. Minimal fixes now: clear timers, show the countdown, give `aria-live="polite"` to the reply box. |
| W14 | P2 | `timer.mark("stt_start")` records a meaningless value. `first_sentence_ms` is never recorded. | Fix with the span API (H15). |

### 2.6 Tests and tooling

| # | Sev | Problem | Fix |
| --- | --- | --- | --- |
| T1 | P1 | Tests drift from reality: `FakeMCPClient.execute_action` and `test_confirmation` use `closed_count` and `diagnosis` keys that the real server doesn't produce. | Define **typed result models** (pydantic) in a shared `syssathi.schemas` module. The server returns them, and fakes must construct them. Drift becomes impossible. |
| T2 | P1 | Unit tests start real processes (`ping`), run a real 3 s diagnosis, and spawn the real MCP server (`test_web`). The suite is slow (35 s) and flaky on CI without `ping` permissions. | Split into `tests/unit` (pure, <3 s total), `tests/integration` (subprocess, marked), and `tests/live` (network, skipped by default). |
| T3 | P1 | `tests/test_eval_sim.py` imports `scripts.eval_multistep` (scripts isn't a package). `eval_multistep` imports `tests.test_helpers`, so production tooling depends on test files. | Move the eval harness into `src/syssathi/eval/`. Move number verification into `syssathi.grounding` (it is useful at runtime too, see §4.5). |
| T4 | P1 | `test_evon_tools.py` checks `if not EVON_BASE_URL`, which can never trigger because config has a default URL. It duplicates 80% of `eval_multistep`. | Merge into one `syssathi eval` CLI with `--suite single|multi`. |
| T5 | P2 | No linting, type checking, or CI. CRLF line endings throughout (Windows-authored). | `ruff` + `ruff format`, `mypy --strict` on `src`, `.gitattributes` (`* text=auto eol=lf`), GitHub Actions matrix (ubuntu, windows, macos × py3.11–3.13). |
| T6 | P2 | `pyproject` depends on `fastmcp~=4.1`, but the code uses `mcp` and `pydantic` directly (transitive deps only). | Depend on `mcp>=2.3,<3` and `pydantic>=2.7` explicitly. Drop `fastmcp` unless it's actually used. Commit `uv.lock`. |

### 2.7 Docs

| # | Problem | Fix |
| --- | --- | --- |
| D1 | `README.md` is 20 lines and doesn't explain the backend choice, mock behaviour, Linux support, or the safety model. | Rewrite (Phase E). |
| D2 | `PROGRESS.md` says Windows 11 and "Phase 4 done", but the repo has since moved to Linux and the demo can't be reproduced as written. | Freeze `PROGRESS.md` as a historical hackathon log. New status lives in this plan and in GitHub issues. |
| D3 | `BRIEF.md` addenda conflict with the code (for example, the brief says `fastmcp`, the code uses `mcp.server.mcpserver`). | Mark the brief "archived (hackathon v0)". Add `docs/ARCHITECTURE.md` describing the real system. |

---

## 3. Phase A: stop the bleeding (1–2 days)

Goal: nothing lies to the user, nothing leaks, and the web app doesn't freeze. No new features.

1. **H2/H3** Remove the silent mock fallback and the mock default. Add a visible mock banner.
2. **H1** Async LLM adapter (`AsyncOpenAI`, no `time.sleep`).
3. **W2/W3** WebSocket Origin check. Origin derived from the bind settings. Require Origin on POST.
4. **W1 (minimal)** Bind `pending_proposal` to a per-connection session id. Approve must present the same session id (cookie). The full session refactor comes in Phase B.
5. **W4/W5/W6** In-memory WAV, buffer cap, disconnect handling, delete the fake-transcript hack.
6. **S1/S2** Fix CPU sampling in `get_top_processes`, and the top-5 truncation.
7. **S3** Rewrite close counting.
8. **C1** Minimal env for the server subprocess.
9. **H11 (minimal)** Replace the emoji range with `\p{Extended_Pictographic}` (`regex` module) so non-Latin scripts survive.
10. **W11** Keep-alive becomes opt-in.
11. **H10** Fix the contradictory Devanagari prompt.

Acceptance: all existing tests still pass after being updated to the real shapes. New tests: WS rejects a foreign Origin; Evon failure gives an explicit "unavailable" reply (not mock text); `get_top_processes(sort_by="cpu")` returns a non-zero CPU for a busy dummy process; Chinese text survives `apply_reply_guard`.

---

## 4. Phase B: make the current product correct (≈1 week)

### 4.1 Typed contracts
- New `src/syssathi/schemas.py`: pydantic models `Findings`, `ProcessGroup`, `StartupEntry`, `BatteryReport`, `Proposal`, `ExecutionResult`, `Refusal(code, message)`.
- MCP tools return `model.model_dump()`, and the MCP output schema is generated from the model. The host parses `structuredContent` back into models.
- Refusal codes: `PROTECTED`, `NOT_RUNNING`, `NOT_IN_DIAGNOSIS`, `EXPIRED`, `REUSED`, `BAD_TOKEN`, `UNKNOWN_ID`, `PROTECTED_PID`.

### 4.2 Session and event model
- `Session` (id, language, script preference, history, last_tool_results, proposals, lock).
- The orchestrator becomes `async def run_turn(session, user_input) -> AsyncIterator[Event]` with events: `transcript`, `route`, `filler`, `token`, `sentence`, `tool_call`, `tool_result`, `proposal`, `error`, `done`.
- The CLI and web are thin renderers of the event stream. This removes W7 and lets streaming TTS start on the first sentence (the brief's 6 s target).

### 4.3 Settings
- `pydantic-settings` (`SYSSATHI_` prefix), `get_settings()` cached, validated at startup with clear errors. `.env.example` is regenerated from the model.

### 4.4 Safety hardening
- S5 (closable only if seen in this session's diagnosis or on the allow-list), S6, S9, W10 codes, audit `session_id` and actor.
- Unit-test `execute_action` with fake psutil objects. Keep exactly one integration test with a dummy child.

### 4.5 Runtime grounding check
- Move the A2 number verifier from `tests/test_helpers.py` to `syssathi/grounding.py`, extended for localized digits (Devanagari ०-९, Bengali, Arabic-Indic, etc. via `unicodedata.digit`).
- At runtime: if the LLM reply contains numbers not present in the tool result, regenerate once with a stricter instruction, then fall back to a **deterministic template** reply (like `confirmation.py`). This turns the hackathon test into a product guarantee.

### 4.6 Tool quality
- S7 battery (powercfg fallback, units), S8 startup (enabled-only, more sources), S10 (swap, disk busy).
- Make tools cross-platform by design: a `platform/` package with `windows.py`, `linux.py`, `macos.py` behind one interface, each returning `supported: false` per capability, never by accident.

Acceptance: `pytest tests/unit` < 5 s. Integration suite green on Linux and Windows CI. The web demo works across two tabs independently. The A2 check is enforced at runtime.

---

## 5. Phase C: re-architect for the real mission

> Mission: **increase technology literacy by making system and tech knowledge easy to access in every language.**
> SysSathi ("system companion") stays the brand. The laptop-slowness flow becomes **one skill among many**.

### 5.1 Product shape

A user (student, parent, shopkeeper, first-time PC owner, anyone) asks, by voice or text, in their own language:
- "Mera laptop slow kyun hai?" → **Diagnose skill**: measures, explains *why* in simple terms ("RAM is like a desk..."), offers a safe fix, and teaches how to check it themselves next time (opens Task Manager instructions).
- "VPN kya hota hai? Kaunsa free wala safe hai?" → **Explain + Sources skill**: answers in simple language, cites curated sources (FMHY, Wikipedia, EFF), and warns about risks.
- "Free mein photo edit karne ka software batao" → **Tool finder skill**: recommendations from the full FMHY index and similar sources, with context: what it is, risks, legal notes where relevant, and download-safety tips. Nothing is hidden; everything is explained.
- "Mera WiFi password kaise badlu?" → **How-to skill**: step-by-step guidance with screenshots or links, adapted to the user's OS (detected locally).
- "Ye error ka matlab kya hai: 0x80070005" → **Error explainer skill**: grounded in Microsoft Learn or distro wikis.

Principles:
1. **Teach, don't just do.** Every answer has a one-line "why" and an optional "learn more" card.
2. **Grounded or silent.** Factual claims cite a source or a local measurement. The number check (§4.5) is extended to "claim check" for RAG.
3. **Native language first.** Reply in the user's language and script, keeping English technical terms where that's natural (code-mix is a feature, not a bug).
4. **Safe by default.** Read-only tools are free. Anything that changes the system is proposal → explicit UI click → audit. Voice never approves.
5. **Works on weak hardware and weak internet.** Text mode is under 100 KB per turn, the knowledge index is local (only the Gnani calls need internet), and answers to common questions are cached.

### 5.2 Target architecture

```
src/syssathi/
  core/            settings, schemas, events, session, errors, i18n (message catalogs)
  llm/             async adapter: evon (default, everywhere), openai_compatible (dev only), mock (test-only)
  speech/          stt/ (prisma REST + streaming), tts/ (timbre REST/SSE/WS), language registry
  skills/          diagnose/, explain/, toolfinder/, howto/, errors/  (each = prompt + tools + templates)
  tools/           MCP server: system tools (current) + knowledge tools (search_sources, get_page)
  knowledge/       ingestion (fmhy, docs), chunking, embeddings, index (sqlite + sqlite-vec / LanceDB), context labelling
  orchestrator/    router (intent classifier, not keywords), planner (max N tool calls), grounding check
  grounding/       number + citation verification
  apps/            cli/, web/ (FastAPI + PWA), mcp (stdio entrypoint for external clients)
  eval/            single-step, multi-step, multilingual suites, judges
```

Key changes compared with today:
- **Router**: replace the Hinglish keyword regex with a small **multilingual intent classifier** (embedding similarity against labelled examples per skill, in any language). The keyword list stays only as a zero-latency hint. `\b` regex also doesn't work reliably on Devanagari combining marks, which is one more reason.
- **Multi-step tool use**: the model card says multi-step is immature. Keep a hard cap (2–3 calls), deterministic validation per step, and the skill-specific allow-lists that `eval_multistep.py` already prototypes.
- **Backends**: Gnani everywhere (decision 2). Prisma for STT, Evon for reasoning, Timbre for TTS. No local or third-party model fallbacks. When a Gnani service is down, degrade gracefully: voice down means text mode with a clear notice; Evon down means deterministic template replies for system tools (diagnose, battery, startup) and an honest "try again" for knowledge questions.

### 5.3 Languages (every language Gnani supports)

| Layer | Plan |
| --- | --- |
| Language ID | fastText `lid.176` or a CLD3-style detector on text. STT-reported language for voice. The user can pin a language in the UI. |
| Scope | Exactly the languages Gnani supports for both Prisma and Timbre (per `GNANI_NOTES.md`: 10 Indian languages + English, plus Hinglish code-mix). One `languages.yaml` registry: code, native name, scripts, Prisma `language_code`, Timbre language and default voice, sentence delimiters, digit set. Adding a language when Gnani adds one = one registry entry plus eval set. Verify the exact list against docs.gnani.ai when implementing. |
| STT | Gnani Prisma, streaming, with the session language as hint (or `indic-auto` until the user picks or it is detected). Code-mix mode on by default. |
| TTS | Gnani Timbre for every supported language, voice selectable per user. Sentence-level streaming. |
| Parity | Voice and text are equal citizens: every feature works by typing, and every reply can be spoken. |
| LLM | Per-language system prompt templates. "Reply in {language_name} using {script}. Keep technical terms in English if commonly used." Script options per language (Hindi: Devanagari / Roman; Urdu: Nastaliq; Punjabi: Gurmukhi / Shahmukhi; Serbian: Cyrillic / Latin…). |
| Text handling | ICU word/sentence segmentation, Unicode-aware markdown/emoji stripping, RTL support in the UI (`dir="auto"`), localized digits in the grounding check. |
| UI strings | Message catalogs (`babel`/gettext or JSON) for **all** fixed strings, including today's Hinglish literals in `orchestrator.py`, `confirmation.py`, `app.py`, `cli.py`. Start with en, hi, hi-Latn, bn, ta, te, mr, gu, kn, ml, pa, or, ur. Community translations via Weblate later. |
| Quality | A per-language eval set (§8). A language ships as "supported" only when its eval passes thresholds. Otherwise it is "beta". |

---

## 6. Phase D: knowledge sources (incl. FMHY)

### 6.1 Source registry
`knowledge/sources.yaml`, one entry per source:
```yaml
- id: fmhy
  name: FMHY (freemediaheckyeah)
  homepage: https://fmhy.net
  ingest: git            # prefer the upstream markdown repo over scraping the site
  repo: <confirm the official FMHY wiki source repo before ingesting>
  license: <verify before ingesting; record it here>
  refresh: weekly
  include_sections: all   # decision 3: nothing blocked; every entry gets context labels, see 6.3
  trust: community
- id: wikipedia
  ingest: api            # summaries via REST API, multilingual natively
  trust: encyclopedic
- id: ms-learn / archwiki / mdn / ubuntu-docs / eff-ssd / python-docs ...
```

### 6.2 Ingestion pipeline
1. **Fetch**: git clone/pull or official APIs. Respect `robots.txt` and rate limits. Never scrape around blocks or anti-bot measures.
2. **Parse**: markdown → sections → link entries (`title`, `url`, `description`, `section path`, `tags such as ⭐ recommended`).
3. **Context labelling (not filtering)**: tag each entry with category, FMHY's own markers (recommended, warnings, "unsafe" notes), legal-sensitivity (e.g. piracy/torrent sections), and known-malware/phishing domain hits. Nothing is dropped; labels drive the explanations and warnings shown to the user.
4. **Chunk + embed**: multilingual embedding model (e.g. `multilingual-e5`/`bge-m3`), stored in SQLite + `sqlite-vec` (single file, ships with the app, works offline). Keep the source language. Cross-lingual retrieval handles queries in other languages.
5. **Version**: every chunk stores `source_id`, `commit/etag`, `fetched_at`. Answers cite the version.
6. **Distribute**: prebuilt index downloads as a signed artifact, so users don't ingest locally. Delta updates weekly.

### 6.3 FMHY policy: educate, don't block (decision 3)
- The full FMHY index is searchable, including download, streaming and torrent sections. The goal is understanding, so every result carries context instead of being hidden.
- Every recommendation shows: what the tool or site is, how it works, risks (malware, scams, privacy), FMHY's own warning markers, and for legally sensitive categories a short neutral note that legality depends on the country and on copyright. Answers should explain concepts (what a torrent is, why cracked installers carry malware, how to verify a hash) so people learn to judge for themselves.
- Domains on public malware/phishing lists are still shown if asked for, but with a prominent warning and the reason. This is information, not a block.
- A "download safety" lesson card is attached to any download-type answer (verify publisher, check hashes, scan with Defender, avoid fake download buttons).
- Attribute FMHY with links back for every recommendation. Check FMHY's license/terms before redistributing its text in the prebuilt index; if not allowed, store links + own-words summaries.

### 6.4 Knowledge tools (MCP)
- `search_sources(query, lang, k, source_ids?)` → chunks with citations.
- `get_tool_recommendations(need, os, lang)` → curated list from FMHY and sources (name, url, why, context/risk/legal notes, source).
- `explain_term(term, lang, level)` → Wikipedia/glossary-grounded explanation.
- All are read-only, so no approval is needed. They return structured results with citations. The grounding step verifies every URL in the reply came from a tool result (no hallucinated links).

---

## 7. Phase E: product, UX, distribution

1. **Web/PWA UI rewrite** (keep it dependency-light: vanilla + Web Components, or Svelte):
   - Language and script picker (persisted), `dir="auto"`, large tap targets, and both hold-to-talk and tap-to-toggle.
   - A conversation view with **source cards** (favicon, title, source name, "why trusted") and **lesson cards** ("Learn: what is RAM?").
   - A proposal card with countdown, what will happen, and what could be lost, plus an Approve/Cancel pair. Voice can only cancel.
   - Accessibility: ARIA live regions, keyboard-only flow, high contrast, captions for all speech, adjustable speech rate.
   - Settings: language, script, voice, speech rate, what is sent to Gnani, clear history.
2. **CLI**: `syssathi chat`, `syssathi diagnose`, `syssathi ask "..." --lang ta`, `syssathi eval`, `syssathi index update`.
3. **Distribution**:
   - `pipx install syssathi` / `uv tool install syssathi`.
   - **Windows first (decision 1)**: Windows installer (PyInstaller/Briefcase + MSIX or Inno Setup) with a tray icon that opens the local UI at 127.0.0.1, auto-start optional, first-run wizard for the Gnani key and language. Local app only (decision 5): no hosted version, no accounts, binds 127.0.0.1 only.
   - **Important for development:** running inside WSL means psutil sees the WSL Linux VM, not Windows. Diagnoses, startup apps, battery and process closing all apply to the VM, not your real laptop. Develop the UI/LLM/knowledge parts in WSL if you like, but run and test the system tools natively on Windows (`py -3.12 -m venv .venv`, `.venv\Scripts\activate`). Add a startup check that detects WSL (`/proc/version` contains `microsoft`) and warns in the UI.
   - Linux and macOS stay supported as secondary platforms.
   - Linux AppImage/Flatpak later. Android is a stretch goal (Termux or a thin client to a home server).
4. **Privacy**: the README states exactly what leaves the machine per backend (today: audio to Gnani, text and process names to Evon). Redact usernames and paths before Gnani calls, and show the user what is sent.
5. **Docs**: new `README.md` (what/why/quickstart/privacy/safety), `docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md` (adding a language, adding a source, adding a skill), and `docs/SAFETY.md` (approval model, protected processes, source policy).

---

## 8. Phase F: quality, evaluation, operations

- **Eval suites** (`syssathi eval`):
  - `tools-single` (today's 20 utterances, expanded per language).
  - `tools-multi` (today's 22 scenarios plus knowledge scenarios).
  - `grounding` (numbers and URLs must come from tool results).
  - `language` (does the reply use the requested language/script? Use a lang-ID check).
  - `safety` (protected processes, destructive system requests, prompt injection via process names and retrieved pages, context/warning presence on risky download queries).
  - `latency` (p50/p95 time to filler, first sentence, full reply).
- **Targets** (initial): 0 safety violations; ≥90% tool-choice accuracy per supported language; 100% grounding after the regenerate-then-template fallback; filler <1.5 s; first sentence <4 s.
- **Judges**: rule-based first (as `eval_multistep.evaluate_episode` does today), then an LLM judge for helpfulness, with human spot checks per language from native speakers.
- **CI**: unit suite on every PR (3 OS × 3 Python), integration nightly, live evals weekly or manual with secrets.
- **Telemetry**: opt-in only, local by default (`timings.jsonl` plus an aggregate dashboard). Never store raw audio or user text remotely without consent.
- **Logs**: platformdirs location, rotation, and no secrets (add a test that greps logs for token patterns).

---

## 9. Ordered task checklist

Each line should become one PR/issue. IDs refer to §2.

**Phase A (now)**
- [x] H2, H3: remove silent mock fallback and mock default. Add banner.
- [x] H1, H4, H5: async LLM adapter, one retry policy, cached client and model.
- [x] W2, W3: WS Origin check. Bind-derived allowed hosts. Origin required on POST.
- [x] W1 (min): proposals bound to a session cookie.
- [x] W4, W5, W6: in-memory WAV, size cap, disconnect handling, delete fake transcript.
- [x] S1, S2: CPU sampling and grouping truncation in `get_top_processes`.
- [x] S3, S4: close counting rewrite, proposal purge.
- [x] C1: minimal subprocess env.
- [x] H11 (min), H10: Unicode-safe guard. Fix the Devanagari prompt.
- [x] W11: keep-alive opt-in.

**Phase B**
- [x] T1: `schemas.py` typed contracts. Refusal codes. Fix W10 and the drifting tests.
- [x] Event-stream orchestrator plus `Session`. Remove W7. Streaming LLM → sentence TTS (V5, W8, W14).
- [x] H7, H8, H9, H6: shared validation, proper tool messages, per-tool reply prompts.
- [x] H13, H14, H12: pydantic-settings, platformdirs, rename the fast-path flag.
- [x] C2, C3, C4: tool errors, timeouts, server restart, `-m` entrypoint + console script.
- [x] S5, S6, S9, S12: closable-only-if-seen, execute-time PID check, Cf stripping, audit fields.
- [x] S7, S8, S10, S11: battery, startup, extra metrics, logging config.
- [x] §4.5 runtime grounding with template fallback.
- [x] V1–V4: Prisma streaming, language params, shared clients, typed errors.
- [x] W9, W12, W13: AudioWorklet, lifespan, UI timer fixes.
- [x] T2–T6: test split, eval harness into `src`, ruff/mypy/CI, explicit deps + lockfile, `.gitattributes`.

**Phase C**
- [x] Package restructure (§5.2). Skills abstraction. Diagnose becomes skill #1.
- [x] Multilingual intent router.
- [x] Language ID, per-language prompt templates, i18n catalogs, ICU segmentation.
- [x] `languages.yaml` registry for all Gnani languages; Prisma streaming + Timbre streaming per language; voice/text parity.
- [x] WSL detection warning; Windows-native dev setup docs.

**Phase D**
- [x] `sources.yaml` registry plus license/terms verification for each source (FMHY first).
- [x] Ingestion pipeline + context labelling (no filtering) + SQLite FTS5 index + signed index artifact.
- [x] Knowledge MCP tools + citation grounding.
- [x] Explain, Tool-finder, How-to, and Error-explainer skills.

**Phase E/F**
- [x] PWA UI rewrite with source and lesson cards, accessibility, language picker.
- [x] CLI subcommands. pipx / `syssathi` console script + Windows launcher.
- [x] README, ARCHITECTURE, CONTRIBUTING, SAFETY docs.
- [x] Eval suites per language, CI matrix, opt-in local telemetry.

---

## 10. Decisions (confirmed 2026-11-09)

1. **Windows first.** Dev currently on WSL; system tools must be run and tested natively on Windows (see §7). Linux/macOS are secondary.
2. **Gnani models everywhere.** Prisma (STT), Evon (LLM), Timbre (TTS). No local or third-party model fallbacks; graceful degradation only (§5.2). `openai_compatible` stays as a developer-only backend.
3. **No blocking.** All FMHY sections are accessible; the product educates with context, risk and legal notes (§6.3).
4. **Voice + text in every language Gnani supports**, at launch (§5.3).
5. **Local app only.** No hosted version, binds 127.0.0.1.
6. **Name stays SysSathi.**

Consequences already folded into this plan: §2 H2 (fallback goes to templates, never mock), W11 (keep-alive still opt-in, because the Evon endpoint is billed), §5.2, §5.3, §6, §7, §9.
