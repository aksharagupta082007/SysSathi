"""MCP client managing the SysSathi MCP server subprocess over stdio."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

# Allowed tools sent to Evon (execute_action is strictly excluded)
ALLOWED_EVON_TOOLS = {
    "diagnose_slowness",
    "get_top_processes",
    "list_startup_apps",
    "get_battery_report",
    "propose_close",
}


def _extract_tool_content(result: Any) -> Any:
    """Extract and parse JSON content from MCP ToolResult."""
    if not hasattr(result, "content") or not result.content:
        return {}
    item = result.content[0]
    text = getattr(item, "text", "")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


class MCPClient:
    """Async MCP client wrapping the stdio server process."""

    def __init__(self, approval_token: str | None = None) -> None:
        self.approval_token = approval_token or secrets.token_hex(16)
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools_cache: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        """Spawn the MCP server as a stdio subprocess and initialize session."""
        if self._session is not None:
            return

        # Locate server.py
        server_script = str(
            Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
        )

        env = dict(os.environ)
        env["SYSSATHI_APPROVAL_TOKEN"] = self.approval_token

        params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env=env,
        )

        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(params)
            )
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            self._exit_stack = exit_stack
            self._session = session

            # Populate tools cache
            tools_result = await session.list_tools()
            for t in tools_result.tools:
                self._tools_cache[t.name] = t
        except Exception:
            await exit_stack.aclose()
            raise

    async def close(self) -> None:
        """Cleanly close session and server subprocess."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            self._tools_cache.clear()

    async def __aenter__(self) -> MCPClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def get_evon_tool_schemas(self) -> list[dict[str, Any]]:
        """Return the 5 allowed tools formatted as OpenAI-compatible function tool schemas."""
        schemas: list[dict[str, Any]] = []
        for name in [
            "diagnose_slowness",
            "get_top_processes",
            "list_startup_apps",
            "get_battery_report",
            "propose_close",
        ]:
            tool = self._tools_cache.get(name)
            if not tool:
                continue

            input_schema = (
                getattr(tool, "input_schema", None)
                or getattr(tool, "inputSchema", None)
                or {"type": "object", "properties": {}}
            )

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": input_schema,
                },
            })
        return schemas

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Get input schema for a specific tool."""
        tool = self._tools_cache.get(tool_name)
        if not tool:
            return None
        return (
            getattr(tool, "input_schema", None)
            or getattr(tool, "inputSchema", None)
            or {"type": "object", "properties": {}}
        )

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on the server and return parsed JSON or text."""
        if not self._session:
            raise RuntimeError("MCP client is not connected.")
        args = arguments or {}
        result = await self._session.call_tool(name, args)
        return _extract_tool_content(result)

