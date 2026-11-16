"""
Provider OpenAI-compatible (OpenAI, OpenRouter, Ollama, Nous Portal, dll).

Menggunakan urllib stdlib — tanpa dependency requests.
Mengirim format Chat Completions + tools, mem-parsing tool_calls.
"""
from __future__ import annotations

import json
import urllib.request

from .base import BaseProvider, Message, ProviderResponse, ToolCall


class OpenAICompatProvider(BaseProvider):
    def __init__(self, model: str, api_base: str, api_key: str = ""):
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key

    def chat(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [self._to_dict(m) for m in messages],
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {"type": "object", "properties": {}})}}
                for t in tools
            ]
            payload["tool_choice"] = "auto"

        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())

        choice = data["choices"][0]["message"]
        tool_calls = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args, id=tc.get("id", "")))
        return ProviderResponse(content=choice.get("content") or "", tool_calls=tool_calls)

    @staticmethod
    def _to_dict(m: Message) -> dict:
        d: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id or tc.name, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in m.tool_calls
            ]
        if m.role == "tool" and m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        return d
