"""SysSathi Command Line Interface (CLI)."""

from __future__ import annotations

import asyncio
import sys

from syssathi.host.mcp_client import MCPClient
from syssathi.host.orchestrator import Orchestrator


async def main() -> None:
    print("Main SysSathi hoon, ek AI assistant.\n")

    async with MCPClient() as mcp:
        orchestrator = Orchestrator(mcp)

        while True:
            try:
                user_input = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAlvida!")
                break

            if not user_input:
                continue

            if user_input in ("/quit", "/exit"):
                print("Alvida!")
                break

            if user_input == "/approve":
                if not orchestrator.pending_proposal:
                    print("SysSathi > Koi pending proposal nahi hai jise approve kiya ja sake.\n")
                    continue

                print("Executing approval...")
                res = await orchestrator.approve()
                if "error" in res or res.get("refused"):
                    print(f"SysSathi > Action execute nahi ho paya: {res.get('reason') or res.get('error')}\n")
                else:
                    closed = res.get("closed_count", 0)
                    skipped = res.get("skipped_count", 0)
                    failed = res.get("failed_count", 0)
                    print(f"SysSathi > Action complete: {closed} band hue, {skipped} skip hue, {failed} fail hue.\n")
                continue

            # Regular message
            reply, timer = await orchestrator.handle_message(user_input)
            print(f"SysSathi > {reply}")
            print(f"          [Time: {timer.total_ms:.1f}ms | Route: {timer.route}]\n")


if __name__ == "__main__":
    asyncio.run(main())

