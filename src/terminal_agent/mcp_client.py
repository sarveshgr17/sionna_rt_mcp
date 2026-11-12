"""Streamable HTTP client connecting to the NVIDIA Sionna RT FastMCP server.

Utilizes the official Python MCP SDK (mcp.client.streamable_http and ClientSession)
to discover registered tools dynamically, inspect schemas, and execute simulation tools
over http://127.0.0.1:8000/mcp with automatic error unwrapping and session resilience.
"""

from contextlib import asynccontextmanager
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger("sionna_rt_mcp.terminal_agent.client")


class MCPClientError(Exception):
    """Raised when an MCP client communication or tool execution fails."""
    pass


class MCPDirectClient:
    """Async Streamable HTTP MCP client for Sionna RT."""

    def __init__(self, server_url: str = "http://127.0.0.1:8000/mcp", timeout_seconds: float = 300.0) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.discovered_tools: Dict[str, Any] = {}
        self.tool_schemas: Dict[str, Dict[str, Any]] = {}
        self._session: Optional[ClientSession] = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._http_client_gen: Any = None
        self.is_connected: bool = False

    async def connect(self) -> Dict[str, Any]:
        """Establishes connection to the MCP server and discovers available tools."""
        try:
            self._http_client_gen = streamable_http_client(self.server_url)
            streams = await self._http_client_gen.__aenter__()
            self._read_stream, self._write_stream = streams[0], streams[1]

            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            # Discover all tools dynamically
            tools_response = await self._session.list_tools()
            self.discovered_tools = {}
            self.tool_schemas = {}

            for tool in tools_response.tools:
                self.discovered_tools[tool.name] = tool
                # Store schema if available
                schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {}))
                self.tool_schemas[tool.name] = schema or {}

            self.is_connected = True
            logger.info("Connected to MCP server at %s. Discovered %d tools.", self.server_url, len(self.discovered_tools))
            return self.discovered_tools

        except (httpx.ConnectError, ConnectionRefusedError, OSError) as exc:
            self.is_connected = False
            raise MCPClientError(
                f"Cannot connect to MCP server at {self.server_url}.\n"
                f"Please ensure the MCP server is running:\n"
                f"  python server.py\n"
                f"Details: {exc}"
            ) from exc
        except Exception as exc:
            self.is_connected = False
            await self.disconnect()
            raise MCPClientError(f"Failed to initialize MCP session with {self.server_url}: {exc}") from exc

    async def disconnect(self) -> None:
        """Closes the active MCP session cleanly."""
        self.is_connected = False
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

        if self._http_client_gen:
            try:
                await self._http_client_gen.__aexit__(None, None, None)
            except Exception:
                pass
            self._http_client_gen = None

    async def __aenter__(self) -> "MCPDirectClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a tool on the MCP server and returns the parsed JSON result."""
        # If not connected or session was closed, connect first
        if not self.is_connected or not self._session:
            await self.connect()

        if tool_name not in self.discovered_tools:
            # Refresh tools in case server was restarted or reloaded
            await self.refresh_tools()
            if tool_name not in self.discovered_tools:
                raise MCPClientError(f"Tool '{tool_name}' is not registered on the MCP server.")

        assert self._session is not None

        try:
            result = await self._session.call_tool(tool_name, arguments)
        except Exception as exc:
            # Connection might have dropped; mark disconnected
            self.is_connected = False
            raise MCPClientError(f"MCP communication error while executing '{tool_name}': {exc}") from exc

        # Check for tool-level error
        is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))

        # Extract content text
        content_text = ""
        if hasattr(result, "content") and result.content:
            for item in result.content:
                if hasattr(item, "text") and item.text:
                    content_text += item.text

        if is_error:
            raise MCPClientError(f"Tool '{tool_name}' failed: {content_text}")

        # Parse JSON return payload
        try:
            return json.loads(content_text)
        except json.JSONDecodeError:
            return {"raw_text": content_text}

    async def refresh_tools(self) -> Dict[str, Any]:
        """Refreshes the dynamic tool catalog."""
        if not self._session:
            return await self.connect()

        tools_response = await self._session.list_tools()
        self.discovered_tools = {}
        self.tool_schemas = {}
        for tool in tools_response.tools:
            self.discovered_tools[tool.name] = tool
            schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {}))
            self.tool_schemas[tool.name] = schema or {}
        return self.discovered_tools

