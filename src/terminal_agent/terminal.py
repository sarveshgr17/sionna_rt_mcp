"""Interactive REPL terminal loop for Sionna RT natural-language radio planning.

Connects to the running MCP server over Streamable HTTP, handles user inputs,
renders banner and formatted metrics, and preserves session context across turns.
"""

import sys
import anyio

from src.terminal_agent.context import SessionContext
from src.terminal_agent.executor import AgentExecutor
from src.terminal_agent.mcp_client import MCPDirectClient, MCPClientError
from src.terminal_agent.presenter import format_welcome_banner


async def run_terminal(server_url: str = "http://127.0.0.1:8000/mcp") -> None:
    """Runs the natural-language terminal client session."""
    client = MCPDirectClient(server_url=server_url)

    print(f"Connecting to Sionna RT MCP server at {server_url}...")
    try:
        await client.connect()
    except MCPClientError as exc:
        print(f"\n[ERROR] Connection failed:\n{exc}")
        return

    # Probe environment for computational backend information
    backend_info = "Unknown"
    try:
        env = await client.call_tool("check_environment", {})
        backend_info = env.get("backend", "CPU LLVM")
    except Exception:
        backend_info = "CPU LLVM (llvm_ad_mono_polarized)"

    banner = format_welcome_banner(
        server_url=server_url,
        backend=backend_info,
        tool_count=len(client.discovered_tools),
    )
    print(banner)

    context = SessionContext()
    executor = AgentExecutor(mcp_client=client, context=context)

    try:
        while True:
            try:
                # Read input in worker thread to prevent blocking the async loop
                user_input = await anyio.to_thread.run_sync(input, "\nYou: ")
            except (EOFError, KeyboardInterrupt):
                print("\n\nExiting Sionna Radio Planner CLI. Goodbye!")
                break

            if not user_input.strip():
                continue

            try:
                result = await executor.execute_instruction(user_input)
                if result.output:
                    print(f"\n{result.output}")
                if result.is_exit:
                    break
            except Exception as exc:
                print(f"\n[ERROR] An unexpected error occurred: {exc}")

    finally:
        await client.disconnect()

