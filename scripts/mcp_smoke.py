"""Smoke test: start MCP server over stdio, list tools, call each, print results."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


async def main() -> None:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    token = secrets.token_hex(16)
    server_script = str(
        PROJECT_ROOT / "src" / "syssathi" / "mcp_server" / "server.py"
    )

    # Pass token and inherit current env
    env = dict(os.environ)
    env["SYSSATHI_APPROVAL_TOKEN"] = token

    params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=env,
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # List tools
            tools_result = await session.list_tools()
            tools = tools_result.tools
            print(f"\n{'='*60}")
            print(f"Registered tools ({len(tools)}):")
            for t in tools:
                print(f"  - {t.name}: {t.description}")
            print(f"{'='*60}\n")

            # 1. diagnose_slowness
            print(">>> diagnose_slowness")
            t0 = time.perf_counter()
            result = await session.call_tool("diagnose_slowness", {})
            elapsed = time.perf_counter() - t0
            data = _extract(result)
            print(f"    Elapsed: {elapsed:.2f}s")
            print(f"    Output: {json.dumps(data, indent=4)}")

            # Validate schema
            import jsonschema
            from syssathi.mcp_server.diagnose import FINDINGS_SCHEMA
            jsonschema.validate(data, FINDINGS_SCHEMA)
            print("    Schema: VALID")
            print()

            # 2. get_top_processes
            print(">>> get_top_processes(limit=3, sort_by='ram')")
            t0 = time.perf_counter()
            result = await session.call_tool(
                "get_top_processes", {"limit": 3, "sort_by": "ram"}
            )
            elapsed = time.perf_counter() - t0
            print(f"    Elapsed: {elapsed:.2f}s")
            print(f"    Output: {json.dumps(_extract(result), indent=4)}")
            print()

            # 3. list_startup_apps
            print(">>> list_startup_apps")
            t0 = time.perf_counter()
            result = await session.call_tool("list_startup_apps", {})
            elapsed = time.perf_counter() - t0
            print(f"    Elapsed: {elapsed:.2f}s")
            print(f"    Output: {json.dumps(_extract(result), indent=4)}")
            print()

            # 4. get_battery_report
            print(">>> get_battery_report")
            t0 = time.perf_counter()
            result = await session.call_tool("get_battery_report", {})
            elapsed = time.perf_counter() - t0
            print(f"    Elapsed: {elapsed:.2f}s")
            print(f"    Output: {json.dumps(_extract(result), indent=4)}")
            print()

            # 5. propose_close on "explorer" — should be refused
            print(">>> propose_close(group_name='explorer')")
            t0 = time.perf_counter()
            result = await session.call_tool(
                "propose_close", {"group_name": "explorer"}
            )
            elapsed = time.perf_counter() - t0
            data = _extract(result)
            print(f"    Elapsed: {elapsed:.2f}s")
            print(f"    Output: {json.dumps(data, indent=4)}")
            assert data.get("refused") is True, "Expected explorer to be refused!"
            print(f"    Correctly refused: {data.get('reason')}")
            print()

    print("Smoke test complete.")


def _extract(result: object) -> dict:
    """Extract dict from MCP CallToolResult."""
    # MCP SDK returns CallToolResult with .content list of TextContent
    if hasattr(result, "content"):
        for block in result.content:
            if hasattr(block, "text"):
                try:
                    return json.loads(block.text)
                except (json.JSONDecodeError, TypeError):
                    continue
    # Fallback
    return json.loads(str(result))


if __name__ == "__main__":
    asyncio.run(main())
