"""MCP client managing the SysSathi MCP server subprocess over stdio."""

from __future__ import annotations

import asyncio
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
    "search_sources",
    "get_tool_recommendations",
    "explain_term",
}


class ToolError(Exception):
    """Raised when an MCP tool fails or reports an error."""

    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name
        self.message = message


def _extract_tool_content(result: Any) -> Any:
    """Extract and parse structured content or JSON from MCP ToolResult."""
    if hasattr(result, "structuredContent") and result.structuredContent is not None:
        return result.structuredContent
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

        # Locate server script or module
        server_script = str(
            Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
        )

        # C1: Pass only a minimal environment to the MCP server subprocess (no API tokens)
        allowed_keys = {
            "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
            "TEMP", "TMP", "USERPROFILE", "HOME", "HOMEPATH", "HOMEDRIVE",
            "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
            "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
            "SYSSATHI_RAM_HIGH_PCT", "SYSSATHI_DISK_LOW_PCT",
            "SYSSATHI_STARTUP_HIGH_COUNT", "SYSSATHI_CPU_HIGH_PCT",
            "SYSSATHI_EXTRA_PROTECTED", "SYSSATHI_LOG_DIR",
        }
        sub_env = {k: v for k, v in os.environ.items() if k.upper() in allowed_keys}
        sub_env["SYSSATHI_APPROVAL_TOKEN"] = self.approval_token

        # C4: prefer -m syssathi.mcp_server with server_script fallback
        args = ["-m", "syssathi.mcp_server"]
        params = StdioServerParameters(
            command=sys.executable,
            args=args,
            env=sub_env,
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
            # Fallback to server_script directly if -m failed
            try:
                params_fallback = StdioServerParameters(
                    command=sys.executable,
                    args=[server_script],
                    env=sub_env,
                )
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(params_fallback)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                self._exit_stack = exit_stack
                self._session = session
                tools_result = await session.list_tools()
                for t in tools_result.tools:
                    self._tools_cache[t.name] = t
            except Exception:
                await exit_stack.aclose()
                raise

    async def check_health(self) -> bool:
        """Verify the MCP server process is responsive; restart if necessary (C3)."""
        if self._session is None:
            try:
                await self.start()
                return True
            except Exception:
                return False
        try:
            await asyncio.wait_for(self._session.list_tools(), timeout=2.0)
            return True
        except Exception:
            logger.warning("MCP server health check failed, restarting subprocess...")
            await self.close()
            try:
                await self.start()
                return True
            except Exception:
                return False

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
        """Return the allowed tools formatted as OpenAI-compatible function tool schemas."""
        schemas: list[dict[str, Any]] = []
        for name in [
            "diagnose_slowness",
            "get_top_processes",
            "list_startup_apps",
            "get_battery_report",
            "propose_close",
            "search_sources",
            "get_tool_recommendations",
            "explain_term",
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
        """Call a tool on the server with timeout and error typing (C2, C3)."""
        if not self._session:
            await self.start()
        if not self._session:
            raise RuntimeError("MCP client is not connected.")

        args = arguments or {}
        timeout = 10.0 if name == "diagnose_slowness" else 5.0

        try:
            result = await asyncio.wait_for(self._session.call_tool(name, args), timeout=timeout)
        except asyncio.TimeoutError:
            raise ToolError(name, f"Timed out after {timeout:.1f}s")
        except Exception as e:
            # If server crashed, attempt one restart
            logger.warning("Tool call exception (%s), attempting MCP restart: %s", name, e)
            await self.close()
            try:
                await self.start()
                if self._session:
                    result = await asyncio.wait_for(self._session.call_tool(name, args), timeout=timeout)
                else:
                    raise ToolError(name, f"Session lost and restart failed: {e}")
            except Exception as e2:
                raise ToolError(name, str(e2)) from e2

        if getattr(result, "isError", False):
            err_content = _extract_tool_content(result)
            raise ToolError(name, str(err_content))

        return _extract_tool_content(result)
