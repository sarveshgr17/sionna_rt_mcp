"""Root-level entry point for running the NVIDIA Sionna RT MCP Server.

Defaults to Streamable HTTP transport (http://127.0.0.1:8000/mcp) for easy
terminal startup and connection from Antigravity, Claude Desktop, or Cursor.
Also supports stdio transport via `--transport stdio`.
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

# 3. Import canonical MCP server instance
from src.mcp_server import create_mcp_server, mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run NVIDIA Sionna RT MCP Server (Streamable HTTP or Stdio)",
    )
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio", "sse"],
        default="streamable-http",
        help="Transport protocol to use (default: streamable-http)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on (default: 8000)",
    )
    parser.add_argument(
        "--endpoint",
        default="/mcp",
        help="Streamable HTTP endpoint path (default: /mcp)",
    )
    args, _ = parser.parse_known_args()

    if args.transport in ("streamable-http", "sse"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = args.endpoint

        print("=" * 72)
        print("          NVIDIA Sionna RT Model Context Protocol (MCP) Server")
        print("=" * 72)
        print(f"  Transport:    Streamable HTTP ({args.transport})")
        print(f"  Binding:      http://{args.host}:{args.port}{args.endpoint}")
        print("  Backend:      CPU LLVM (llvm_ad_mono_polarized)")
        print(f"  Working Dir:  {project_root}")
        print("  Status:       Ready for AI Client connections (Antigravity / Claude)")
        print("-" * 72)
        print("  Antigravity Configuration (~/.gemini/config/mcp_config.json):")
        print("    {")
        print('      "mcpServers": {')
        print('        "sionna-rt": {')
        print(f'          "url": "http://{args.host}:{args.port}{args.endpoint}"')
        print("        }")
        print("      }")
        print("    }")
        print("=" * 72)
        print("Press CTRL+C to stop the server.\n")

        mcp.run(transport=args.transport)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

