"""MCP server — registers all diagnostic and action tools.

Uses mcp.server.mcpserver.MCPServer (mcp SDK 2.x, formerly FastMCP).
Logging goes to stderr only. Nothing is written to stdout except MCP protocol.
"""

from __future__ import annotations

import logging
import sys
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

# Module logger (logging configuration moved to main() per S11)
logger = logging.getLogger("syssathi.mcp_server")

mcp = MCPServer("SysSathi")


@mcp.tool()
async def diagnose_slowness() -> dict[str, Any]:
    """Sample CPU, RAM, disk and processes for 3 seconds and return findings."""
    from syssathi.mcp_server.diagnose import run_diagnosis
    return await run_diagnosis()


@mcp.tool()
async def get_top_processes(
    limit: Annotated[int, Field(ge=1, le=10, description="Number of process groups to return")] = 5,
    sort_by: Annotated[Literal["ram", "cpu"], Field(description="Sort groups by ram or cpu usage")] = "ram",
) -> dict[str, Any]:
    """Return the top process groups sorted by RAM or CPU usage."""
    import platform
    if platform.system() not in ("Windows", "Linux", "Darwin"):
        return {"supported": False}

    from syssathi.mcp_server.processes import sample_processes
    # Fetch all groups without pre-truncating to 5
    groups = await sample_processes(window_s=0.5, top_n=None)

    key = "ram_mb" if sort_by == "ram" else "cpu_pct"
    groups.sort(key=lambda g: g[key], reverse=True)

    try:
        from syssathi.mcp_server.actions import record_seen_groups
        record_seen_groups([g["name"] for g in groups if isinstance(g, dict) and "name" in g])
    except Exception:
        pass

    return {"groups": groups[:limit]}


@mcp.tool()
async def list_startup_apps() -> dict[str, Any]:
    """List startup apps from registry Run keys and Startup folders."""
    from syssathi.mcp_server.startup import list_startup_apps as _list
    return await _list()


@mcp.tool()
async def get_battery_report() -> dict[str, Any]:
    """Report battery charge, power source, and health percentage."""
    from syssathi.mcp_server.battery import get_battery_report as _get
    return await _get()


@mcp.tool()
async def propose_close(
    group_name: Annotated[str, Field(description="Process group name to propose closing")],
) -> dict[str, Any]:
    """Propose closing a process group. Returns action_id or refusal."""
    import asyncio
    from syssathi.mcp_server.actions import propose_close as _propose
    return await asyncio.to_thread(_propose, group_name)


@mcp.tool()
async def execute_action(
    action_id: Annotated[str, Field(description="The action_id from a proposal")],
    approval_token: Annotated[str, Field(description="Approval token for authorization")],
) -> dict[str, Any]:
    """Execute a previously proposed close action after approval."""
    from syssathi.mcp_server.actions import execute_action as _execute
    return await _execute(action_id, approval_token)


@mcp.tool()
async def search_sources(
    query: Annotated[str, Field(description="Search query to search across FMHY, Wikipedia, MS Learn, EFF")],
    lang: Annotated[str, Field(description="Language code hint, e.g. en, hi")] = "en",
    k: Annotated[int, Field(ge=1, le=10, description="Maximum number of results to return")] = 5,
) -> dict[str, Any]:
    """Search curated sources for tools, tutorials, error explanations, and tech concepts."""
    import asyncio
    from syssathi.mcp_server.knowledge import search_sources as _search
    return await asyncio.to_thread(_search, query, lang, k)


@mcp.tool()
async def get_tool_recommendations(
    need: Annotated[str, Field(description="Software need or category, e.g. 'photo editing', 'torrent', 'pdf'")],
    os_name: Annotated[str, Field(description="Target operating system, e.g. 'windows'")] = "windows",
    lang: Annotated[str, Field(description="Language code hint")] = "en",
) -> dict[str, Any]:
    """Get curated software recommendations with download safety tips and risk notes."""
    import asyncio
    from syssathi.mcp_server.knowledge import get_tool_recommendations as _get_recs
    return await asyncio.to_thread(_get_recs, need, os_name, lang)


@mcp.tool()
async def explain_term(
    term: Annotated[str, Field(description="Computing term or error code to explain, e.g. 'RAM', 'VPN', '0x80070005'")],
    lang: Annotated[str, Field(description="Language code hint")] = "en",
    level: Annotated[Literal["beginner", "advanced"], Field(description="Target explanation level")] = "beginner",
) -> dict[str, Any]:
    """Look up an encyclopedic or troubleshooting explanation for a tech term or error."""
    import asyncio
    from syssathi.mcp_server.knowledge import explain_term as _explain
    return await asyncio.to_thread(_explain, term, lang, level)


def main() -> None:
    """Run SysSathi MCP server over stdio."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
