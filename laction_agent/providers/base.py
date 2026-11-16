"""Kontrak provider LLM: pesan masuk, tool call / teks keluar."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ProviderResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class BaseProvider(ABC):
    model: str = "unknown"

    @abstractmethod
    def chat(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        """Kirim percakapan + skema tools, terima respons (teks dan/atau tool calls)."""
        raise NotImplementedError
