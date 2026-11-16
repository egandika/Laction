"""
Context Compressor — jaga percakapan panjang agar tidak meledak.

Strategi (mirip Hermes, versi ringan):
1. System prompt selalu dilindungi.
2. Riwayat sebelum user terakhir diringkas jadi satu pesan.
3. Satu turn terakhir (user + tool calls + tool results) dipertahankan utuh
   supaya provider OpenAI-compatible tidak menerima tool message yatim.
"""
from __future__ import annotations

import json

from .providers.base import Message
from .utils import truncate


def estimate_tokens(messages: list[Message]) -> int:
    total = 0
    for m in messages:
        total += len(m.content or "") // 4
        for tc in m.tool_calls or []:
            total += len(tc.name) // 4
            total += len(json.dumps(tc.arguments, ensure_ascii=False, default=str)) // 4
    return total


def _summarize(middle: list[Message]) -> str:
    if not middle:
        return "(tidak ada riwayat sebelumnya)"
    bits: list[str] = []
    for m in middle:
        if m.role in ("user", "assistant") and m.content:
            bits.append(f"{m.role}: {m.content[:160]}")
        elif m.role == "tool" and m.content:
            bits.append(f"tool: {m.content[:100]}")
        elif m.tool_calls:
            bits.append("tool_calls: " + ", ".join(tc.name for tc in m.tool_calls))
    return truncate(" | ".join(bits), 4000)


def _shrink(m: Message, max_chars: int) -> Message:
    return Message(
        role=m.role,
        content=truncate(m.content or "", max(120, max_chars)),
        tool_calls=m.tool_calls,
        tool_call_id=m.tool_call_id,
    )


def compress(messages: list[Message], limit: int = 8000) -> list[Message]:
    # PERHATIAN: jangan pakai shortcut `len(messages) <= 6`. Lima tool result
    # berukuran 8000 karakter sudah ~10k token tapi tetap 6 pesan — versi lama
    # membiarkannya lewat tanpa kompresi. Yang aman: <= 3 pesan (system + user
    # + satu balasan) memang tidak ada yang bisa diringkas.
    if estimate_tokens(messages) <= limit or len(messages) <= 3:
        return messages

    system: list[Message] = []
    body = messages
    if messages and messages[0].role == "system":
        system = [messages[0]]
        body = messages[1:]

    last_user = None
    for i, m in enumerate(body):
        if m.role == "user":
            last_user = i

    if last_user is not None:
        middle, tail = body[:last_user], body[last_user:]
    else:
        tail = body[-4:]
        while tail and tail[0].role == "tool":
            tail = tail[1:]
        middle = body[:-len(tail)] if tail else body

    summary = _summarize(middle)
    summary_msg = Message(
        role="user",
        content=f"[Ringkasan percakapan sebelumnya — jangan panggil ulang tool dari bagian ini]\n{summary}",
    )

    result = system + [summary_msg] + tail
    while estimate_tokens(result) > limit and len(summary) > 200:
        summary = summary[: max(200, len(summary) // 2)].rstrip() + " …"
        result = system + [Message(role="user", content=f"[Ringkasan percakapan sebelumnya]\n{summary}")] + tail

    if estimate_tokens(result) > limit and tail:
        max_chars = max(200, (limit * 3) // max(1, len(tail)))
        tail = [_shrink(m, max_chars) for m in tail]
        result = system + [Message(role="user", content=f"[Ringkasan percakapan sebelumnya]\n{summary}")] + tail

    return result
