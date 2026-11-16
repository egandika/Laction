"""Minimal stdlib MCP (Model Context Protocol) client — JSON-RPC 2.0 over stdio."""
from __future__ import annotations

from .client import MCPError, MCPStdioClient
from .registry import MCPRegistry

__all__ = ["MCPError", "MCPRegistry", "MCPStdioClient"]
