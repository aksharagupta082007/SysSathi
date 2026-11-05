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
| 4 | LLM adapter, prompts, router, timing | not started |
| 5 | MCP client, orchestrator, CLI, utterances.jsonl | not started |
| 6 | Live Evon test (Phase 2 done) | not started |
| 7 | Gnani docs notes and probe script | not started |
| 8 | Voice clients and sentence streaming | not started |
| 9 | FastAPI backend and push-to-talk page | not started |
| 10 | Approve flow and re-measure speech (Phase 4 done) | not started |

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
