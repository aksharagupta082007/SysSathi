"""SysSathi Command Line Interface (CLI) supporting subcommands (Phase E §7.2).

Usage:
  syssathi chat                           Interactive multilingual companion
  syssathi diagnose                       Instant hardware and resource diagnosis
  syssathi ask "Mera laptop slow kyun hai" Single-turn answer with sources & lesson cards
  syssathi eval                           Run evaluation scenarios
  syssathi index update                   Verify or rebuild local knowledge index
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from syssathi.host.config import get_llm_backend
from syssathi.host.mcp_client import MCPClient
from syssathi.host.orchestrator import Orchestrator, Session
from syssathi.knowledge.index import get_knowledge_index
from syssathi.knowledge.ingest import compute_index_manifest


async def cmd_chat(args: argparse.Namespace) -> int:
    """Interactive multilingual companion chat."""
    backend = get_llm_backend()
    if backend == "mock":
        print("************************************************")
        print("  [DEMO / MOCK MODE] Using simulated backend   ")
        print("************************************************\n")

    print("Main SysSathi hoon, aapka tech companion.")
    print("Commands: /approve, /status, /lang <latin|devanagari>, /help, /quit\n")

    async with MCPClient() as mcp:
        orchestrator = Orchestrator(mcp)
        session = Session(session_id="cli_session", language=args.lang)

        while True:
            try:
                user_input = (await asyncio.to_thread(input, "You > ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAlvida!")
                break

            if not user_input:
                continue

            if user_input in ("/quit", "/exit"):
                print("Alvida!")
                break

            if user_input in ("/help", "/?"):
                print("SysSathi CLI Commands:")
                print("  /approve              - Approve pending process close action")
                print("  /status               - Show backend, MCP, and pending proposal status")
                print("  /lang <latin|native>  - Switch script / reply style")
                print("  /quit                 - Exit SysSathi\n")
                continue

            if user_input == "/status":
                mcp_alive = await mcp.check_health()
                print("--- SysSathi Status ---")
                print(f"  Backend: {backend}")
                print(f"  MCP Server: {'connected' if mcp_alive else 'disconnected'}")
                print(f"  Language: {session.language}")
                print(f"  Script preference: {session.script}")
                prop = session.pending_proposal or orchestrator.pending_proposal
                if prop:
                    print(f"  Pending proposal: {prop.get('description')}")
                else:
                    print("  Pending proposal: None")
                print("-----------------------\n")
                continue

            if user_input.startswith("/lang"):
                parts = user_input.split()
                if len(parts) > 1 and parts[1].lower() in ("latin", "devanagari", "native"):
                    session.script = parts[1].lower()
                    print(f"Script preference set to: {session.script}\n")
                else:
                    print("Usage: /lang latin OR /lang devanagari\n")
                continue

            if user_input == "/approve":
                prop = session.pending_proposal or orchestrator.pending_proposal
                if not prop:
                    print("SysSathi > Koi pending proposal nahi hai jise approve kiya ja sake.\n")
                    continue

                print("Executing approval...")
                res = await orchestrator.approve(session)
                if "error" in res or res.get("refused"):
                    print(f"SysSathi > Action execute nahi ho paya: {res.get('reason') or res.get('error')}\n")
                else:
                    closed = res.get("closed", res.get("closed_count", 0))
                    skipped = res.get("skipped", res.get("skipped_count", 0))
                    failed = res.get("failed", res.get("failed_count", 0))
                    print(f"SysSathi > Action complete: {closed} band hue, {skipped} skip hue, {failed} fail hue.\n")
                continue

            # Regular message via streaming turn
            timer_data: dict[str, Any] = {}
            reply_text = ""
            lesson_card: dict[str, Any] | None = None
            sources: list[dict[str, Any]] = []

            async for evt in orchestrator.run_turn(session, user_input):
                if evt.type == "proposal":
                    print(f"SysSathi [Proposal] > {evt.data.get('description')} (Type /approve to confirm)")
                elif evt.type == "reply":
                    reply_text = evt.text
                elif evt.type == "lesson_card":
                    lesson_card = evt.data
                elif evt.type == "sources":
                    sources.extend(evt.data.get("results") or evt.data.get("recommendations") or evt.data.get("sources") or [])
                elif evt.type == "done":
                    timer_data = evt.data

            print(f"SysSathi > {reply_text}")

            if lesson_card:
                print(f"\n💡 [Learn] {lesson_card.get('title')}: {lesson_card.get('summary')}")
                if lesson_card.get("actionable_tip"):
                    print(f"   Tip: {lesson_card.get('actionable_tip')}")

            if sources:
                print("\n📚 [Sources & Tools]")
                for s in sources[:3]:
                    name = s.get("name") or s.get("title")
                    url = s.get("url")
                    print(f"   • {name} ({url})")

            total_ms = timer_data.get("total_ms", 0.0)
            if total_ms > 0:
                print(f"   (Turn completed in {total_ms:.0f}ms)\n")
            else:
                print()

    return 0


async def cmd_diagnose(args: argparse.Namespace) -> int:
    """Run direct system diagnosis."""
    print("Sampling CPU, RAM, Disk and Processes...")
    async with MCPClient() as mcp:
        findings = await mcp.call_tool("diagnose_slowness", {})
        battery = await mcp.call_tool("get_battery_report", {})
        startup = await mcp.call_tool("list_startup_apps", {})

    print("\n================ SYSTEM DIAGNOSTIC REPORT ================")
    if isinstance(findings, dict):
        cpu = findings.get("cpu_avg_pct", 0)
        ram = findings.get("ram_used_pct", 0)
        ram_gb = findings.get("ram_total_gb", 0)
        disk_free = findings.get("disk_free_pct", 0)
        print(f"CPU Average:   {cpu:.1f}%")
        print(f"RAM Usage:     {ram:.1f}% of {ram_gb:.1f} GB")
        print(f"Disk Free:     {disk_free:.1f}%")

        top_groups = findings.get("top_groups", [])
        if top_groups:
            print("\nTop Heavy Processes:")
            for g in top_groups[:4]:
                print(f"  • {g.get('name', 'unknown')}: {g.get('ram_mb', 0):.0f} MB RAM, {g.get('cpu_pct', 0):.1f}% CPU ({g.get('procs', 1)} processes)")

    if isinstance(battery, dict) and battery.get("has_battery"):
        plugged = "Plugged In" if battery.get("plugged") else "On Battery"
        health = f", Health: {battery.get('health_pct')}%" if battery.get("health_pct") is not None else ""
        print(f"\nBattery:       {battery.get('charge_pct')}% ({plugged}){health}")

    if isinstance(startup, dict):
        print(f"Startup Apps:  {startup.get('count', 0)} enabled apps")

    print("=========================================================\n")
    return 0


async def cmd_ask(args: argparse.Namespace) -> int:
    """Ask a single question with grounded citations."""
    question = args.question.strip()
    if not question:
        print("Error: Empty question provided.")
        return 1

    async with MCPClient() as mcp:
        orchestrator = Orchestrator(mcp)
        session = Session(session_id="cli_ask", language=args.lang, script=args.script)

        reply_text = ""
        lesson_card = None
        sources = []

        async for evt in orchestrator.run_turn(session, question):
            if evt.type == "reply":
                reply_text = evt.text
            elif evt.type == "lesson_card":
                lesson_card = evt.data
            elif evt.type == "sources":
                sources.extend(evt.data.get("results") or evt.data.get("recommendations") or evt.data.get("sources") or [])

        print(f"\nSysSathi > {reply_text}")

        if lesson_card:
            print(f"\n💡 [Learn] {lesson_card.get('title')}: {lesson_card.get('summary')}")
            if lesson_card.get("actionable_tip"):
                print(f"   Tip: {lesson_card.get('actionable_tip')}")

        if sources:
            print("\n📚 [Sources & Recommendations]")
            for s in sources[:3]:
                name = s.get("name") or s.get("title")
                url = s.get("url")
                tip = s.get("download_safety_tips", [""])[0] if s.get("download_safety_tips") else ""
                print(f"   • {name} ({url})")
                if tip:
                    print(f"     Safety: {tip}")

        print()
    return 0


async def cmd_eval(args: argparse.Namespace) -> int:
    """Run evaluation scenarios."""
    print("Running SysSathi evaluation suite...")
    from syssathi.eval.multistep import run_multistep_eval
    async with MCPClient() as mcp:
        res = await run_multistep_eval(mcp)
        print(f"\nEvaluation Complete: {res.get('passed', 0)}/{res.get('total', 0)} scenarios passed.")
    return 0


async def cmd_index(args: argparse.Namespace) -> int:
    """Inspect or update local knowledge index."""
    idx = get_knowledge_index()
    valid = idx.verify_index_integrity()
    print(f"Knowledge Database: {idx.db_path}")
    print(f"Integrity Check:    {'PASS' if valid else 'FAIL'}")

    if idx.db_path != ":memory:" and idx.db_path.exists():
        manifest = compute_index_manifest(idx.db_path)
        print(f"File Size:          {manifest['file_size_bytes']:,} bytes")
        print(f"SHA-256 Digest:     {manifest['sha256']}")
        print(f"Signed:             {manifest['signed']}")
    return 0


async def cmd_telemetry(args: argparse.Namespace) -> int:
    """Display local performance and latency telemetry dashboard."""
    from syssathi.core.telemetry import compute_summary_stats, render_dashboard_text
    stats = compute_summary_stats()
    print(render_dashboard_text(stats))
    return 0


def main() -> None:
    """CLI entrypoint parsing subcommands."""
    parser = argparse.ArgumentParser(
        prog="syssathi",
        description="SysSathi — Multilingual Windows Tech Companion",
    )
    subparsers = parser.add_subparsers(dest="command")

    # chat subcommand
    p_chat = subparsers.add_parser("chat", help="Start interactive conversation companion")
    p_chat.add_argument("--lang", default="hi", help="Initial language code (default: hi)")

    # diagnose subcommand
    subparsers.add_parser("diagnose", help="Run hardware and system resource diagnosis")

    # ask subcommand
    p_ask = subparsers.add_parser("ask", help="Ask a tech question with citations")
    p_ask.add_argument("question", help="The question to ask")
    p_ask.add_argument("--lang", default="hi", help="Language code (default: hi)")
    p_ask.add_argument("--script", default="latin", help="Script preference: latin or native")

    # eval subcommand
    subparsers.add_parser("eval", help="Run evaluation scenarios")

    # index subcommand
    p_index = subparsers.add_parser("index", help="Inspect knowledge index")
    p_index.add_argument("action", nargs="?", default="status", choices=["status", "update"], help="Action to perform")

    # telemetry subcommand
    subparsers.add_parser("telemetry", help="View local performance and latency telemetry dashboard")

    args = parser.parse_args()

    if not args.command:
        # Default to interactive chat if no subcommand passed
        args.command = "chat"
        args.lang = "hi"

    handlers = {
        "chat": cmd_chat,
        "diagnose": cmd_diagnose,
        "ask": cmd_ask,
        "eval": cmd_eval,
        "index": cmd_index,
        "telemetry": cmd_telemetry,
    }

    handler = handlers.get(args.command, cmd_chat)
    code = asyncio.run(handler(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
