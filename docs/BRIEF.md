# SysSathi: build brief for the coding agent

## 1. Your job

You are building SysSathi, a voice assistant that finds out why a Windows laptop is slow and answers in Hinglish. Read this whole brief before you write code.

Work in the phases in section 11. Do Phase 1 and Phase 2 now, then stop and report. Do not start Phase 3 until I say so. Start by writing a short plan (files and order) and wait for my approval. Where this brief says "ask", stop and ask me instead of guessing.

## 2. Context

- This is a hackathon entry built on Gnani AI models: Prisma (speech to text), Evon (LLM), Timbre (text to speech). The deadline I was given is Nov 10, 2026, 11:59 PM IST. Today is Nov 5, 2026. Speed matters, but correctness of the safety rules matters more.
- Demo story: I hold a button and say "Mera laptop slow chal raha hai". The system samples the laptop for 3 seconds, finds the cause, and answers by voice in Hinglish, for example: "RAM 91% use ho rahi hai. Chrome ke 14 processes 3.1 GB le rahe hain. Band kar dun?" I click Approve. The system closes Chrome, measures again, and says "RAM 91% se 64% ho gaya."
- Target machine: Windows 10 or 11. You are running on that machine, so psutil reads the real laptop. If the OS is not Windows, tell me, and make Windows-only tools return `{"supported": false}`.
- Language: Python 3.11 or newer.

## 3. Fixed architecture decisions

Do not change these without asking me.

1. Everything except the three Gnani models runs on the laptop in one Python host app. A remote model cannot call tools on my laptop, so the host app is the MCP client. It sends Evon the user text and tool schemas, receives a tool call, runs it through MCP, and sends the result back.
2. The MCP server is a subprocess of the host over stdio. No network port. The server must never write to stdout except through the MCP protocol. Log to stderr or a file.
3. Prisma, Timbre and Evon are outbound API calls only.
4. Evon sits behind an adapter with three backends: `evon_remote` (OpenAI-compatible HTTP), `openai_compatible` (any other endpoint, for fallback) and `mock` (deterministic, for offline tests, clearly labelled in logs).
5. Keyword fast path: if the user text matches slowness keywords, the host calls `diagnose_slowness` directly and skips LLM tool choice. Evon then only explains the result. Everything else goes to Evon with free tool choice. A config flag `FORCE_FAST_PATH` (default true) turns the fast path off so I can test Evon routing.
6. Tools return findings that already applied fixed thresholds. Evon narrates the findings and never infers causes.
7. Two-phase actions. Evon can only propose a close. Only the host UI can execute, after I click Approve. Voice never approves anything.
8. Spoken replies are plain text, 40 words or fewer, no markdown, no emoji.
9. Text-only deliverables. No diagrams.

## 4. Evon endpoint (deployed and tested)

- Base URL: `https://6aec3eed62710132ca850c91.endpoints.huggingface.cloud/v1`, from env `EVON_BASE_URL`. Token from env `HF_TOKEN`. Model id from env `EVON_MODEL`; if unset, call `client.models.list()` and use the first id.
- It runs vLLM with `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nano_v3`. On Nov 5 a test with one tool schema returned a correct tool call in 0.14 to 0.15 s and a correct no-tool answer on an unrelated question in 0.09 s. That test ran from a notebook, so expect different numbers from the laptop.
- Use the `openai` Python package. Request settings: `temperature=0.6`, `top_p=0.95`, `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`. Strip any `<think>...</think>` block from the reply before it goes anywhere else.
- Gnani's model card says multi-step tool use is still in development, and no tool-use scores are published. So: allow at most one tool call per user turn. Validate every returned tool name against the allowlist in section 7 and every argument set against its JSON schema (use `jsonschema`). On an invalid call, log it and use a safe reply asking me to repeat.
- The endpoint may scale to zero. Use a 30 second timeout with one retry on the first call, and log a clear message if it fails.

## 5. Prisma and Timbre (Phase 3 only)

- Read https://docs.gnani.ai before writing any Phase 3 code. Do not guess endpoints, headers or audio formats. Timbre docs: `https://docs.gnani.ai/api/TTS/tts-inference` (REST), `/tts-sse` (streaming), `/tts-websocket` (realtime), `/available-voices`. If you cannot reach the docs, stop and ask me to paste the relevant section.
- Prisma v3.0: output modes Verbatim, Transcribe, Code-mix and Transliterate, set per request. Streaming and REST. Keyterm prompting (up to 200 terms) and language hints. Defaults for us: mode from env `PRISMA_MODE` (default Code-mix), candidate languages Hindi and English, keyterms from a list of app names in config (Chrome, Teams, Spotify, OneDrive, Edge, Zoom).
- Timbre v3.0: streaming or WebSocket. Voice from env `TIMBRE_VOICE`. Reply style from env `REPLY_STYLE`: `latin` (Hinglish in Roman letters) or `devanagari_mixed` (Hindi in Devanagari, English words in Latin). Timbre's handling of Roman Hinglish is undocumented, so I will compare both by ear.
- Key from env `GNANI_API_KEY`.

## 6. Repository layout

Create this structure.

```
syssathi/
  pyproject.toml
  .env.example
  .gitignore            (must include .env and logs/)
  README.md             (how to run, in 15 lines or fewer)
  src/syssathi/
    mcp_server/
      server.py         (FastMCP app, registers tools)
      diagnose.py
      processes.py
      startup.py
      battery.py
      actions.py
      policy.py         (protected list, thresholds)
      sanitize.py
      audit.py
    host/
      config.py
      llm.py            (adapter and three backends)
      router.py
      mcp_client.py
      orchestrator.py
      prompts.py
      timing.py
      cli.py
    voice/              (Phase 3)
    web/                (Phase 3)
  tests/
    utterances.jsonl
  scripts/
    mcp_smoke.py
    test_evon_tools.py
  logs/                 (gitignored)
```

Dependencies for Phases 1 and 2: `fastmcp` (server and client, check its current docs, do not rely on memory), `psutil`, `openai`, `httpx`, `python-dotenv`, `jsonschema`, `pytest`, `pytest-asyncio`. Ask before adding anything else.

## 7. MCP server specification

### Tools

| Tool | Evon can call | Arguments | Returns |
| --- | --- | --- | --- |
| `diagnose_slowness` | yes | none | Findings JSON (below) |
| `get_top_processes` | yes | `limit` int 1 to 10, `sort_by` "ram" or "cpu" | Process groups |
| `list_startup_apps` | yes | none | Entries with name and source, plus count |
| `get_battery_report` | yes | none | Charge %, plugged, designed capacity, full-charge capacity, health % |
| `propose_close` | yes | `group_name` string | `action_id`, description, `expires_in_s` |
| `execute_action` | no | `action_id`, `approval_token` | Result and a fresh `diagnose_slowness` result |

The host must send Evon only the first five tool schemas. The server still registers `execute_action`. Tool descriptions are one line each, because Evon reads them on every request.

### Findings JSON

```json
{
  "cpu_avg_pct": 78.4,
  "cpu_peak_pct": 96.0,
  "ram_used_pct": 91.2,
  "ram_total_gb": 15.8,
  "disk_free_pct": 14.0,
  "disk_mb_per_s": 3.2,
  "top_groups": [{"name": "chrome", "procs": 14, "ram_mb": 3100, "cpu_pct": 22.1}],
  "startup_apps": 11,
  "findings": [{"code": "RAM_HIGH", "message": "RAM above 85%", "severity": "high"}]
}
```

Thresholds live in `policy.py` and can be overridden by env vars. Starting values: `RAM_HIGH` above 85% used, `DISK_LOW` below 10% free, `STARTUP_HIGH` more than 8 entries, `CPU_HIGH` above 80% average over the window.

### Implementation rules

- `diagnose_slowness` uses one 3-second window. Prime per-process `cpu_percent()` at the start and read it at the end. Sample overall CPU every 0.5 s for the average and the peak. Read disk read and write bytes at both ends of the window for MB/s. `psutil.cpu_percent()` returns a meaningless 0.0 on its first call, so never use a single instant reading.
- Per-process CPU can exceed 100 on multi-core machines. Divide by `psutil.cpu_count()`.
- Group processes by lowercase executable name without `.exe`. Sum RAM (RSS) and CPU. Return the top 5 groups. Skip processes that raise `AccessDenied` or `NoSuchProcess`.
- Disk free is for the system drive (`%SystemDrive%`).
- Startup apps: read the `Run` keys under HKCU and HKLM with `winreg`, plus the two Startup folders. Do not return command lines.
- Battery health: `psutil.sensors_battery()` has no health value and returns None on desktops. Read `BatteryStaticData` (designed capacity) and `BatteryFullChargedCapacity` from WMI namespace `root\wmi` with a PowerShell `Get-CimInstance` call: fixed arguments, no shell, 10 second timeout, JSON output. Health = full-charge / designed. If unavailable, return `{"has_battery": false}` or `{"health_available": false}`.
- Blocking psutil calls must not block the server loop. Run them in worker threads.
- Sanitize every string that comes from the machine (process names, startup names): truncate to 40 characters and strip control characters. Never return command lines or full paths.

### Actions

- `propose_close(group_name)`: refuse if the group is not running or is protected. Snapshot every process in the group as `(pid, name, create_time)`. Store the proposal in memory with a UUID `action_id` and a 60 second expiry. Return a description such as "Close Chrome: 14 processes, 3.1 GB. Unsaved work may be lost." Close nothing.
- `execute_action(action_id, approval_token)`: check the token with a constant-time compare against env `SYSSATHI_APPROVAL_TOKEN` (the host generates it with `secrets.token_hex(16)` on each run and passes it to the server subprocess). Check the proposal exists, is unexpired and unused. For each snapshot entry, re-check that name and create time still match. Skip mismatches. Call `terminate()`, wait up to 3 s, then `kill()` any survivors. Mark the proposal used. Return counts of closed, skipped and failed. Then run a fresh `diagnose_slowness` and include it.
- Protected: `System`, `System Idle Process`, `Registry`, `smss`, `csrss`, `wininit`, `winlogon`, `services`, `lsass`, `svchost`, `explorer`, `dwm`, `fontdrvhost`, `MsMpEng`, `SecurityHealthService`, any group whose name contains `python`, and the PIDs of the host, the MCP server and their parents.
- `audit.py` appends one JSON line to `logs/audit.jsonl` per proposal, execution and refusal: timestamp, tool, `action_id`, group, PIDs, result.

## 8. Host specification

- `config.py` loads `.env`. Every key in section 4 and 5 plus thresholds and the keyword list live here. `.env.example` lists all of them with empty values. Never put a secret in code, logs or tests.
- `router.py`: lowercase the text, strip punctuation, and match the keyword list from config (starting list: slow, hang, lag, laggy, dheema, dhima, atak, freeze, "slow chal"). A match returns route `fast`. Otherwise route `evon`.
- `orchestrator.py`:
  - `fast`: call `diagnose_slowness` through the MCP client, then one Evon call with the reply prompt and the findings JSON.
  - `evon`: Evon call 1 with the five tool schemas and the last 6 messages (tool results truncated to 2,000 characters). If it returns a tool call, validate it, run it, then Evon call 2 with the tool result. If it returns no tool call, its content is the reply.
  - Reject any tool name outside the five allowed names, even if the model returns one.
- `llm.py`: one interface, `chat(messages, tools=None) -> ChatResult`, three backends as in section 3. The `mock` backend returns a fixed Hinglish reply built from the findings and can simulate tool calls from a keyword table.
- `timing.py`: write one JSON line per request to `logs/timings.jsonl` with `route`, `llm1_ms`, `tool_ms`, `llm2_ms`, `total_ms` (Phase 3 adds `stt_ms`, `first_sentence_ms`, `tts_first_byte_ms`).
- `cli.py`: a loop that reads typed lines and prints the reply and timings. `/approve` approves the pending proposal. `/quit` exits. Print "Main SysSathi hoon, ek AI assistant." at startup.

### Prompts (`prompts.py`)

Reply system prompt:

```
You are SysSathi, an AI assistant that explains why a Windows laptop is slow.
You receive a JSON object called findings, measured a few seconds ago.
Reply in Hinglish (Hindi written in Roman letters, with English technical words).
Plain text only, at most 40 words, no markdown, no emoji, no lists.
Use only numbers and names that appear in the JSON.
Mention at most two problems, most serious first.
Never invent causes. If findings is empty, say the laptop looks healthy.
If a proposal is present, end by asking whether to close it.
```

Add a second variant for `REPLY_STYLE=devanagari_mixed`: "Write Hindi words in Devanagari and keep English technical words in Latin script."

Tool-routing system prompt (for the `evon` route): "You help diagnose a slow Windows laptop. Call one tool when it answers the question. Do not call a tool for unrelated questions. To close an app, call propose_close with a group name from the latest diagnosis."

## 9. Safety rules (hard requirements)

1. Evon never receives `execute_action`. Only host code calls it, only after my click (Phase 4) or `/approve` (CLI).
2. No `shell=True` anywhere. No free-text strings from the model or the transcript reach a subprocess.
3. No `open_application` tool in this MVP.
4. Tests that close processes use a harmless dummy child process only (for example `ping -t 127.0.0.1`, group name `ping`). Never run a test that closes Chrome, Explorer or anything I use.
5. The MCP server binds no port.
6. Process and startup names are untrusted text. Sanitize before they enter any prompt.
7. Say in the README that audio and process names leave the machine (Gnani speech APIs, and the Evon endpoint). Do not describe the system as fully local.

## 10. Voice loop rules (Phase 3, for later)

- FastAPI backend plus one static HTML page. Push-to-talk by holding a button. The browser captures the mic with `echoCancellation` and `noiseSuppression` enabled. The page shows the transcript, the reply text, the proposal and an Approve button.
- Stream Prisma over its streaming endpoint. Stream Evon tokens and send each finished sentence to Timbre. Mute the mic while audio plays.
- When the router picks `fast`, play a short filler ("Ek second, check karta hoon") immediately.
- Targets (my estimates, measure them): filler within 2 s of the end of speech, first diagnosis sentence within 6 s, full reply generated within 8 s.

## 11. Phases and acceptance criteria

### Phase 1: MCP server (do now)

Build everything in section 7 and `scripts/mcp_smoke.py`, which starts the server over stdio, lists tools and prints the output of each. Done when:

- All tests pass (`pytest`).
- `mcp_smoke.py` runs `diagnose_slowness` in 3.0 to 4.5 s on this machine, and the output validates against the findings schema.
- With many Chrome tabs open, Chrome appears as one group in `top_groups`.
- `propose_close` on a protected group, an unknown group and an expired proposal is refused and logged.
- `execute_action` works on a dummy `ping` process, and fails with a wrong token, a reused `action_id` and a changed create time.
- Nothing is written to stdout by the server except MCP messages.

### Phase 2: Host and Evon (do now, after Phase 1)

Build section 8, the three LLM backends, and `scripts/test_evon_tools.py`. Done when:

- Typing "mera laptop slow chal raha hai" in the CLI prints a Hinglish reply of 40 words or fewer in which every number appears in the findings JSON.
- Unit tests cover: router keywords, tool-name allowlist, argument validation, `<think>` stripping, and the mock backend. They run offline.
- `tests/utterances.jsonl` holds 20 utterances: 8 slowness phrasings in Hinglish and English, 4 specific questions (battery, startup apps, RAM, disk), 4 action requests ("Chrome band kar do"), 4 refusals ("explorer band kar do", "delete my files", a request to close the host app, one unrelated question). Each has the acceptable tool names or "none".
- `test_evon_tools.py` runs all 20 against the real endpoint with the fast path off and prints a table: utterance, expected, actual, latency in ms, pass or fail, then the total passed.

### Phase 3 and 4: not yet

Voice and web UI (Phase 3), then Approve button and the re-measure speech (Phase 4). Wait for my go.

## 12. Working rules for you

- Plan first, then wait for my approval.
- Run `pytest` before you say a phase is done. Show me the output.
- Show terminal commands before running any that install packages or create virtual environments. Never run a command that closes a process outside the tests described above.
- Keep code simple: type hints, small functions, comments only where the reason is not obvious.
- If a library's real API differs from this brief, say so and propose the change. Do not change it silently.
- Do not add features, tools or abstractions that this brief does not ask for.
- End each phase with a report: what you built, how to run it, test results, any deviation from this brief, and open questions.

---

## Addendum (overrides earlier text where they conflict)

A1. Fast path proposal. After diagnose_slowness on the fast path, if findings contain RAM_HIGH or CPU_HIGH, the host picks the first group in top_groups that policy.py does not mark protected and calls propose_close with that group name. Evon does not choose the group on the fast path. The proposal goes into the data sent to the reply prompt. Execution still needs my click or /approve.

A2. Number check (test helper only, no schema change). A number in a reply is valid if it equals a number in the findings JSON, equals one rounded to a whole number, or equals a group's ram_mb divided by 1000 rounded to one decimal.

A3. Reply guard. Before any reply is printed or spoken, the host removes markdown characters and emoji, then cuts the text to 40 words, ending at the last sentence end inside the limit. If there is no sentence end, cut at 40 words.

A4. Router. Match whole words and whole phrases on the normalized text. Never match a keyword inside a longer word.

A5. Approve endpoint (Phases 3 and 4). The web server binds 127.0.0.1 only. The Approve route requires a random nonce that the server puts in the page at load and the page sends as a header. It rejects any request whose Origin or Host is not the local server. The approval token never reaches the browser.

A6. Sessions. I run the work in parts. Each session prompt names its part and replaces the "do Phase 1 and Phase 2 now, then stop" instruction in section 1. Build only the named part. docs/PROGRESS.md carries state between parts.