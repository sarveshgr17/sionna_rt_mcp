# Windows 11 Runtime Setup and Execution Guide

This guide describes how to configure, reproduce, and verify the NVIDIA Sionna RT Model Context Protocol (MCP) server environment on native Windows 11.

---

## 1. System Requirements

- **Operating System:** Windows 11 64-bit (Build 22000 or later).
- **Processor:** Intel Core i5/i7/i9 (10th Gen or newer) or AMD Ryzen (3000 series or newer) with AVX2 instruction support.
- **System Memory (RAM):** 16 GB minimum recommended.
- **Disk Space:** 5 GB free disk space.
- **Target Backend:** Mitsuba 3 CPU LLVM (`llvm_ad_mono_polarized`).
  > [!NOTE]
  > Mitsuba 3 and Dr.Jit on native Windows do not support NVIDIA CUDA/OptiX GPU acceleration due to Windows LLVM/PTX toolchain constraints. Simulation executes via the high-performance CPU LLVM JIT backend.

---

## 2. Python Environment Setup

### 2.1 Python Installation
Install **CPython 3.10.10 64-bit** from [python.org](https://www.python.org/downloads/release/python-31010/):
- Ensure "Add Python 3.10 to PATH" is checked during installation.
- Verify installation:
  ```powershell
  py -3.10 --version
  # Output: Python 3.10.10
  ```

> [!WARNING]
> Do **not** use Python 3.14+ for Sionna RT simulations. Precompiled binary wheels for `mitsuba` and `drjit` are not available for Python 3.14 on Windows. Python 3.10.10 is the strictly verified version.

### 2.2 Create Virtual Environment
From the project root (`C:\Users\eulo_\Downloads\sionna_rt_mcp-main`):

```powershell
# Navigate to the repository root
cd C:\Users\eulo_\Downloads\sionna_rt_mcp-main

# Create dedicated virtual environment
C:\Users\eulo_\AppData\Local\Programs\Python\Python310\python.exe -m venv .venv_sionna

# Activate virtual environment
.\.venv_sionna\Scripts\Activate.ps1
```

### 2.3 Install Dependencies
Upgrade `pip` and install the verified project dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install matplotlib
```

Installed core package baseline:
- `sionna-rt==2.2.0`
- `mitsuba==3.9.1`
- `drjit==1.5.0`
- `mcp==1.30.0`
- `numpy==2.2.6`
- `matplotlib==3.10.9`
- `pytest==9.2.0`

---

## 3. LLVM Standalone Configuration (Windows-Specific)

### 3.1 Why Standalone LLVM is Required
Dr.Jit requires `LLVM-C.dll` to perform runtime JIT compilation for CPU ray tracing. On Windows, if a full LLVM toolchain (e.g., LLVM 18.1.6 with `clang.exe`, `lld.exe`, etc.) is added to the system `PATH`, Windows DLL search resolution can inadvertently load conflicting C-runtime or GCC runtime DLLs, resulting in an **Access Violation `0xC0000005`** or heap corruption.

### 3.2 The Isolated DLL Configuration
The verified solution isolates `LLVM-C.dll` in its own directory:
- **Location:** `C:\Users\eulo_\LLVM-standalone\LLVM-C.dll`
- Size: ~124 MB (LLVM 18.1.6 64-bit).

### 3.3 Required Windows Restrictions
1. **DO NOT** add the full LLVM `bin` directory to the system `PATH`.
2. **DO NOT** call `os.add_dll_directory()` on the general LLVM installation directory.
3. **DO NOT** attempt to force CUDA/OptiX variants on Windows.

### 3.4 Environment Variables
Set the following environment variables in your PowerShell session before running simulations:

```powershell
$env:DRJIT_LIBLLVM_PATH = "C:\Users\eulo_\LLVM-standalone\LLVM-C.dll"
$env:DRJIT_LIBCUDA_PATH = "DISABLED"
$env:DRJIT_LIBOPTIX_PATH = "DISABLED"
$env:PYTHONIOENCODING = "utf-8"
```

To make these permanent for your Windows user profile:
```powershell
[Environment]::SetEnvironmentVariable("DRJIT_LIBLLVM_PATH", "C:\Users\eulo_\LLVM-standalone\LLVM-C.dll", "User")
[Environment]::SetEnvironmentVariable("DRJIT_LIBCUDA_PATH", "DISABLED", "User")
[Environment]::SetEnvironmentVariable("DRJIT_LIBOPTIX_PATH", "DISABLED", "User")
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")
```

---

## 4. Verification Procedures

Execute these verification commands sequentially to confirm that the environment is fully operational.

### 4.1 Environment Diagnostic Check
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv_sionna\Scripts\python.exe scripts/verify_env.py
```
**Expected Output:**
```text
============================================================
       Sionna RT Environment Verification
============================================================
[✓] Python: Python 3.10.10
[✓] Sionna RT: sionna-rt v2.2.0
    Active Backend: llvm_ad_mono_polarized (CPU LLVM)
[✓] Scene Loading: Loaded built-in scene 'simple_reflector'
============================================================
RESULT: Environment is ready for Sionna RT simulations! ✓
```

### 4.2 Full Regression Test Suite
Run the automated pytest suite covering all 11 test modules:
```powershell
.\.venv_sionna\Scripts\python.exe -m pytest -v
```
**Expected Result:** `194 passed, 20 subtests passed` in ~25 seconds.

### 4.3 Point-to-Point MCP Verification
Verify that the MCP server can execute point-to-point ray tracing over stdio:
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv_sionna\Scripts\python.exe scripts/verify_mcp_client.py
```
**Expected Result:** 6/6 steps pass, finding 2 propagation paths (LOS and Specular Reflection) with ~66.8 dB total path loss.

### 4.4 Radio Map MCP Workflow Verification
Verify the complete radio-map simulation, heatmap generation, storage, and comparison workflow:
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv_sionna\Scripts\python.exe scripts/verify_radio_map_workflow.py
```
**Expected Result:** All 7 verification steps pass, validating $+10.0$ dBm power scaling and $B - A$ spatial difference computation.

---

## 5. Running the MCP Server & Client Integrations

The server supports two transport protocols: **Streamable HTTP** (recommended for Antigravity, Claude, and remote agents) and **Stdio** (for local CLI processes).

### 5.1 Method 1: Streamable HTTP Mode (Recommended)
Start the server from the terminal:
```powershell
.\.venv_sionna\Scripts\python.exe server.py
```
This binds to `http://127.0.0.1:8000/mcp` and displays:
```text
========================================================================
          NVIDIA Sionna RT Model Context Protocol (MCP) Server
========================================================================
  Transport:    Streamable HTTP (streamable-http)
  Binding:      http://127.0.0.1:8000/mcp
  Backend:      CPU LLVM (llvm_ad_mono_polarized)
  Working Dir:  C:\Users\eulo_\Downloads\sionna_rt_mcp-main
  Status:       Ready for AI Client connections (Antigravity / Claude)
========================================================================
```

#### Antigravity Configuration
To connect Antigravity to the running server, add the server entry in `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "sionna-rt": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```
Antigravity automatically connects, discovers all seven tools, and provides access to Sionna RT simulations directly in chat.

### 5.2 Method 2: Standalone Stdio Mode
To run the server as a local subprocess over standard input/output:
```powershell
# Option A: via server.py
.\.venv_sionna\Scripts\python.exe server.py --transport stdio

# Option B: directly via src/mcp_server.py
.\.venv_sionna\Scripts\python.exe src/mcp_server.py
```
The server listens for JSON-RPC messages on standard input and writes responses to standard output.

### 5.3 Claude Desktop Configuration

**Option A (Streamable HTTP with `python server.py` running):**
```json
{
  "mcpServers": {
    "sionna-rt": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**Option B (Stdio subprocess):**
Add to `%APPDATA%\Claude\claude_desktop_config.json`:

Path: `%APPDATA%\Claude\claude_desktop_config.json`

Add the following entry under `"mcpServers"`:

```json
{
  "mcpServers": {
    "sionna-rt": {
      "command": "C:\\Users\\eulo_\\Downloads\\sionna_rt_mcp-main\\.venv_sionna\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\eulo_\\Downloads\\sionna_rt_mcp-main\\src\\mcp_server.py"
      ],
      "env": {
        "DRJIT_LIBLLVM_PATH": "C:\\Users\\eulo_\\LLVM-standalone\\LLVM-C.dll",
        "DRJIT_LIBCUDA_PATH": "DISABLED",
        "DRJIT_LIBOPTIX_PATH": "DISABLED",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

Restart Claude Desktop. All 7 MCP tools (`check_environment`, `list_scenes`, `run_simulation`, `generate_radio_map`, `list_experiments`, `get_experiment_details`, `compare_experiments`) will appear in the tool picker.

### 5.3 Cursor Configuration
In Cursor Settings $\to$ Features $\to$ MCP:
1. Click **+ Add New MCP Server**.
2. **Name:** `sionna-rt`
3. **Type:** `command`
4. **Command:** `C:\Users\eulo_\Downloads\sionna_rt_mcp-main\.venv_sionna\Scripts\python.exe src/mcp_server.py`

