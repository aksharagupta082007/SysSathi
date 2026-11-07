"""Test Evon tool-calling behavior on 20 utterances against the live endpoint (Phase 2c)."""

from __future__ import annotations

import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from syssathi.host.config import EVON_BASE_URL, HF_TOKEN
from syssathi.host.llm import chat
from syssathi.host.mcp_client import ALLOWED_EVON_TOOLS, MCPClient
from syssathi.host.prompts import TOOL_ROUTING_PROMPT

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_evon_tools")


async def main() -> None:
    # 1. Check required env vars
    if not EVON_BASE_URL:
        print("ERROR: EVON_BASE_URL is not set in .env")
        sys.exit(1)
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN is not set in .env")
        sys.exit(1)

    # 2. Load utterances
    utterances_file = PROJECT_ROOT / "tests" / "utterances.jsonl"
    if not utterances_file.exists():
        print(f"ERROR: {utterances_file} does not exist")
        sys.exit(1)

    utterances: list[dict[str, Any]] = []
    with open(utterances_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                utterances.append(json.loads(line))

    print(f"Loaded {len(utterances)} test utterances.")

    # 3. Retrieve tool schemas from MCP server (list tools only, NO tool execution)
    print("Retrieving tool schemas from MCP server...")
    async with MCPClient() as mcp:
        tool_schemas = mcp.get_evon_tool_schemas()
        # Create map of tool name -> schema for jsonschema validation
        tool_schema_map = {
            t["function"]["name"]: t["function"]["parameters"]
            for t in tool_schemas
        }

    print(f"Retrieved {len(tool_schemas)} allowed tool schemas: {list(tool_schema_map.keys())}\n")

    # 4. Run utterances against live Evon endpoint
    results: list[dict[str, Any]] = []
    invalid_tool_calls = 0

    print(f"{'#':<3} | {'Category':<10} | {'Status':<6} | {'Latency':<8} | {'Expected':<22} | {'Actual':<22} | {'Utterance'}")
    print("-" * 110)

    for idx, item in enumerate(utterances, start=1):
        text = item["text"]
        cat = item.get("category", "")
        expected = item.get("expected", ["none"])
        expected_args = item.get("expected_args")

        messages = [
            {"role": "system", "content": TOOL_ROUTING_PROMPT},
            {"role": "user", "content": text},
        ]

        t0 = time.perf_counter()
        try:
            chat_result = chat(messages=messages, tools=tool_schemas, backend="evon_remote")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as err:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            print(f"{idx:<3} | {cat:<10} | ERROR  | {elapsed_ms:>6.1f}ms | {str(expected):<22} | ERROR: {err} | {text}")
            results.append({
                "idx": idx,
                "text": text,
                "category": cat,
                "expected": expected,
                "actual": "error",
                "passed": False,
                "latency_ms": elapsed_ms,
                "error": str(err),
            })
            continue

        actual_tool = "none"
        actual_args: dict[str, Any] = {}
        is_invalid = False

        if chat_result.tool_calls:
            tc = chat_result.tool_calls[0]
            actual_tool = tc.name
            actual_args = tc.arguments or {}

            # Validate tool name against allowlist
            if actual_tool not in ALLOWED_EVON_TOOLS:
                is_invalid = True
                invalid_tool_calls += 1
            else:
                # Validate arguments against jsonschema
                schema = tool_schema_map.get(actual_tool)
                if schema:
                    try:
                        jsonschema.validate(actual_args, schema)
                    except jsonschema.ValidationError:
                        is_invalid = True
                        invalid_tool_calls += 1

        # Check pass/fail
        passed = False
        if not is_invalid and actual_tool in expected:
            if expected_args:
                # Case-insensitive comparison for group_name
                exp_grp = str(expected_args.get("group_name", "")).lower()
                act_grp = str(actual_args.get("group_name", "")).lower()
                if exp_grp == act_grp:
                    passed = True
            else:
                passed = True

        status = "PASS" if passed else "FAIL"
        act_display = actual_tool if not actual_args else f"{actual_tool}({list(actual_args.values())[0]})"
        exp_display = str(expected[0] if len(expected) == 1 else expected)

        print(f"{idx:<3} | {cat:<10} | {status:<6} | {elapsed_ms:>6.1f}ms | {exp_display:<22} | {act_display:<22} | {text}")

        results.append({
            "idx": idx,
            "text": text,
            "category": cat,
            "expected": expected,
            "actual": actual_tool,
            "actual_args": actual_args,
            "passed": passed,
            "latency_ms": elapsed_ms,
        })

    # Summary statistics
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    latencies = [r["latency_ms"] for r in results]
    median_lat = statistics.median(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0

    print("\n" + "=" * 60)
    print("EVON LIVE TEST SUMMARY")
    print("=" * 60)
    print(f"Total Utterances:       {total}")
    print(f"Passed:                 {passed_count} / {total} ({passed_count/total*100:.1f}%)")
    print(f"Invalid Tool Calls:     {invalid_tool_calls}")
    print(f"Median Latency:         {median_lat:.1f} ms")
    print(f"Max Latency:            {max_lat:.1f} ms")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

