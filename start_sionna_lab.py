#!/usr/bin/env python3
"""Unified launcher for the full Sionna Lab Workstation.

Starts:
1. NVIDIA Sionna RT FastMCP Server (Streamable HTTP on port 8000)
2. Sionna Lab Backend Adapter (Starlette / Uvicorn on port 8080)
3. React / Vite Frontend (port 5173)
"""

import os
import signal
import socket
import subprocess
import sys
import time

project_root = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(project_root, ".venv", "bin", "python")
if not os.path.isfile(venv_python):
    venv_python = sys.executable

processes = []


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def signal_handler(sig, frame):
    print("\n[Sionna Lab] Shutting down all services...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            p.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def free_ports(ports=(8000, 8080, 5173)):
    """Release ports if occupied by stale processes to prevent Errno 98."""
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    cmd = f"lsof -ti :{port} 2>/dev/null || fuser {port}/tcp 2>/dev/null || true"
                    out = subprocess.check_output(cmd, shell=True).decode().strip()
                    for p in out.split():
                        try:
                            pid = int(p.strip())
                            if pid != os.getpid():
                                print(f"  [*] Port {port} in use by PID {pid}. Releasing port...")
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(0.3)
                                os.kill(pid, signal.SIGKILL)
                        except Exception:
                            pass
        except Exception:
            pass


def main():
    free_ports()
    lan_ip = get_lan_ip()
    print("=" * 72)
    print("      SIONNA LAB — Wireless Propagation Simulation Workstation")
    print("=" * 72)
    print("  [1] Starting MCP Server (Streamable HTTP: 0.0.0.0:8000/mcp)...")
    p_mcp = subprocess.Popen(
        [venv_python, "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"],
        cwd=project_root,
    )
    processes.append(p_mcp)
    time.sleep(1.5)

    print("  [2] Starting Backend Adapter (Starlette REST & Artifacts: 0.0.0.0:8080)...")
    p_adapter = subprocess.Popen(
        [venv_python, "adapter/server.py"],
        cwd=project_root,
    )
    processes.append(p_adapter)
    time.sleep(1.5)

    print("  [3] Starting Vite Frontend (Dual-Stack [::]:5173)...")
    frontend_dir = os.path.join(project_root, "frontend")
    import shutil
    bun_bin = shutil.which("bun") or (
        os.path.expanduser("~/.bun/bin/bun")
        if os.path.exists(os.path.expanduser("~/.bun/bin/bun"))
        else None
    )
    if bun_bin and os.path.exists(bun_bin):
        frontend_cmd = [bun_bin, "run", "dev", "--", "--host", "::", "--port", "5173"]
    else:
        npm_bin = shutil.which("npm") or "npm"
        frontend_cmd = [npm_bin, "run", "dev", "--", "--host", "::", "--port", "5173"]

    p_vite = subprocess.Popen(
        frontend_cmd,
        cwd=frontend_dir,
    )
    processes.append(p_vite)

    print("-" * 72)
    print("  ✓ All services active:")
    print("    • Workstation UI:  http://localhost:5173")
    print(f"                       http://127.0.0.1:5173")
    print(f"                       http://{lan_ip}:5173 (WSL/Network Host)")
    print("    • Backend Adapter: http://localhost:8080")
    print("    • MCP Endpoint:    http://localhost:8000/mcp")
    print("-" * 72)
    print("  Press Ctrl+C to terminate all services.\n")

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"[!] Process {p.pid} exited unexpectedly. Stopping stack...")
                    signal_handler(None, None)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()

