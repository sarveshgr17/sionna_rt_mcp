"""Root-level entry point for the Sionna RT Natural-Language Terminal Client.

Connects to the active MCP server over Streamable HTTP and provides an interactive
natural-language conversational console for wireless radio planning simulations.

Usage:
    python cli.py
    python cli.py --server-url http://127.0.0.1:8000/mcp
"""

import argparse
import os
import sys

# 1. Enforce working directory at project root
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 2. Enforce Windows standalone LLVM environment configuration
_llvm_standalone = r"C:\Users\eulo_\LLVM-standalone\LLVM-C.dll"
if os.path.isfile(_llvm_standalone):
    os.environ.setdefault("DRJIT_LIBLLVM_PATH", _llvm_standalone)
    os.environ.setdefault("DRJIT_LIBCUDA_PATH", "DISABLED")
    os.environ.setdefault("DRJIT_LIBOPTIX_PATH", "DISABLED")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import anyio
from src.terminal_agent.terminal import run_terminal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sionna RT Conversational Natural-Language Terminal Client",
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8000/mcp",
        help="Streamable HTTP endpoint of the running MCP server (default: http://127.0.0.1:8000/mcp)",
    )
    args = parser.parse_args()

    try:
        anyio.run(run_terminal, args.server_url)
    except KeyboardInterrupt:
        print("\nExiting CLI. Goodbye!")


if __name__ == "__main__":
    main()

