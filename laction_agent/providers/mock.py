"""
MockProvider — LLM palsu untuk demo & test tanpa API key.

Dia "memahami" perintah Bahasa Indonesia sederhana, mengubahnya jadi
tool calls, lalu merangkai hasil tool menjadi jawaban akhir. Dengan ini
seluruh loop agent (memory, tools, skills, sub-agent) bisa dicoba
end-to-end tanpa biaya dan tanpa jaringan.

Contoh:
- "list file" / "ls"                 -> list_files
- "baca file README.md"              -> read_file
- "tulis file catatan.txt isi halo"  -> write_file
- "jalankan echo halo"               -> run_terminal
- "ingat: saya suka kopi"            -> memory_save
- "apa yang kamu ingat?"             -> memory_read
- "cari ingatan kopi"                -> memory_search
- "buat skill kopi: langkah 1..."    -> create_skill
- "list skill" / "lihat skill kopi"  -> list_skills / view_skill
- "list tool" / "jam berapa"         -> list_tools / get_time
- "delegasikan: list file"           -> delegate_task
"""
from __future__ import annotations

import re

from ..utils import truncate
from .base import BaseProvider, Message, ProviderResponse, ToolCall


class MockProvider(BaseProvider):
    def __init__(self, model: str = "mock-laction-1"):
        self.model = model
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"mock-call-{self._counter}"

    @staticmethod
    def _last_user(messages: list[Message]) -> str:
        for m in reversed(messages):
            if m.role == "user":
                return m.content.strip()
        return ""

    @staticmethod
    def _trailing_tool_results(messages: list[Message]) -> list[Message]:
        """Ambil tool result sejak assistant tool_calls terakhir."""
        out: list[Message] = []
        for m in reversed(messages):
            if m.role == "tool":
                out.append(m)
            elif m.role == "assistant" and m.tool_calls:
                break
            elif m.role in ("user", "system"):
                break
        return list(reversed(out))

    def chat(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        # Setelah tool dieksekusi, jangan panggil tool yang sama lagi.
        tool_results = self._trailing_tool_results(messages)
        if tool_results:
            user_text = truncate(self._last_user(messages), 200)
            results = "\n\n".join(
                f"• {truncate((t.content or '').strip(), 1400)}" for t in tool_results
            )
            return ProviderResponse(
                content=(
                    f"Selesai ✅ Saya sudah menjalankan tool untuk: \"{user_text}\"\n\n"
                    f"Hasil:\n{results}\n\n"
                    f"[mock:{self.model}] Mode mock merangkai jawaban dari hasil tool. "
                    "Dengan LLM sungguhan, ringkasannya akan lebih natural dan kontekstual."
                )
            )

        user_text = self._last_user(messages)
        text = user_text.lower()

        # --- Memory (baca dulu sebelum pola simpan) ---
        if re.search(r"\b(apa|tampilkan|lihat|baca|daftar)\b.*\b(ingat|ingatan|memori|memory)\b", text) or text in ("memori", "memory", "list memory"):
            return ProviderResponse(tool_calls=[ToolCall("memory_read", {}, self._next_id())])

        m = re.search(r"(?:cari|telusuri)\s+(?:ingatan|riwayat|memory)\s*[:\s]\s*(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("memory_search", {"query": m.group(1).strip()}, self._next_id())])

        m = re.search(r"(?:ingat|hafal|catat)\s*:\s*(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if not m:
            m = re.match(r"(?:ingat|hafal|catat)\s+(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("memory_save", {"note": m.group(1).strip()}, self._next_id())])

        m = re.search(r"(?:preferensi|profil user|user)\s*:\s*(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("user_save", {"note": m.group(1).strip()}, self._next_id())])

        # --- File ---
        m = re.search(r"baca file\s+(\S+)", user_text, re.IGNORECASE)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("read_file", {"path": m.group(1)}, self._next_id())])

        m = re.search(r"tulis file\s+(\S+)\s+isi\s+(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("write_file", {"path": m.group(1), "content": m.group(2).strip()}, self._next_id())])

        m = re.match(r"(?:list file|ls|daftar file|list files)\s*(.*)", user_text, re.IGNORECASE)
        if m:
            rest = m.group(1).strip()
            if rest.startswith("-"):
                # Normalisasi ke `ls`, jadi "list file -la" tidak jadi
                # perintah shell "list file -la" yang tidak ada.
                return ProviderResponse(tool_calls=[ToolCall("run_terminal", {"command": "ls " + rest}, self._next_id())])
            return ProviderResponse(tool_calls=[ToolCall("list_files", {"path": rest or "."}, self._next_id())])

        # --- Terminal & web ---
        m = re.search(r"(?:jalankan|eksekusi|run)\s+(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("run_terminal", {"command": m.group(1).strip()}, self._next_id())])

        m = re.search(r"(?:buka web|buka|fetch|ambil halaman)\s+(https?://\S+)", user_text, re.IGNORECASE)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("web_fetch", {"url": m.group(1)}, self._next_id())])

        # --- Skills ---
        m = re.search(r"buat skill\s+([\w\-]+)[:\s]+(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("create_skill", {"name": m.group(1), "content": m.group(2).strip()}, self._next_id())])

        m = re.search(r"(?:lihat|baca|pakai|gunakan)\s+skill\s+([\w\-]+)", user_text, re.IGNORECASE)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("view_skill", {"name": m.group(1)}, self._next_id())])

        if "list skill" in text or "daftar skill" in text:
            return ProviderResponse(tool_calls=[ToolCall("list_skills", {}, self._next_id())])

        # --- Cron ---
        m = re.search(r"(?:hapus cron|cron remove)\s+([\w\-]+)", user_text, re.IGNORECASE)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("cron_remove", {"name": m.group(1)}, self._next_id())])

        if "list cron" in text or "daftar cron" in text:
            return ProviderResponse(tool_calls=[ToolCall("cron_list", {}, self._next_id())])

        m = re.search(r"(?:tambah cron|cron add)\s+([\w\-]+)\s*\|\s*(.+?)\s*\|\s*(\d+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("cron_add", {"name": m.group(1), "task": m.group(2).strip(), "interval_seconds": int(m.group(3))}, self._next_id())])

        # --- Delegasi & sistem ---
        m = re.search(r"(?:delegasikan|delegate)\s*[:\-]?\s*(.+)", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            return ProviderResponse(tool_calls=[ToolCall("delegate_task", {"task": m.group(1).strip()}, self._next_id())])

        if "list tool" in text or "daftar tool" in text or "tool apa" in text:
            return ProviderResponse(tool_calls=[ToolCall("list_tools", {}, self._next_id())])

        if "jam berapa" in text or "waktu sekarang" in text or "tanggal sekarang" in text or text in ("waktu", "tanggal"):
            return ProviderResponse(tool_calls=[ToolCall("get_time", {}, self._next_id())])

        if "info agent" in text or "versi agent" in text:
            return ProviderResponse(tool_calls=[ToolCall("agent_info", {}, self._next_id())])

        # --- Pencarian file (catch-all untuk "cari ...") ---
        m = re.search(r"(?:cari|carikan|grep|temukan)\s+(?:teks|text|file|di file|dalam file)?\s*[\"']?(.+?)[\"']?\s*$", user_text, re.IGNORECASE | re.DOTALL)
        if m:
            query = m.group(1).strip()
            args = {"query": query}
            ext = re.search(r"\bext\s*[:=]?\s*(\.[a-z0-9]+)", query, re.IGNORECASE)
            if ext:
                args["ext"] = ext.group(1).lower()
                args["query"] = query.replace(ext.group(0), "").strip() or query
            return ProviderResponse(tool_calls=[ToolCall("search_files", args, self._next_id())])

        # --- Jawaban teks biasa ---
        help_text = (
            "Perintah yang saya pahami: 'list file', 'baca file README.md', "
            "'tulis file x.txt isi halo', 'jalankan echo halo', 'ingat: saya suka kopi', "
            "'apa yang kamu ingat?', 'cari ingatan kopi', 'list skill', "
            "'buat skill nama: langkah...', 'list tool', 'jam berapa', "
            "'delegasikan: list file', 'list cron'."
        )
        if any(w in text for w in ("halo", "hai", "hello", "help", "bantuan", "tolong")):
            return ProviderResponse(
                content=f"Halo! Saya Laction Agent (mode mock, tanpa API key). {help_text}"
            )
        if "terima kasih" in text or "makasih" in text:
            return ProviderResponse(content="Sama-sama! Ada lagi yang bisa saya bantu?")
        return ProviderResponse(
            content=(
                f"[mock:{self.model}] Saya menerima: \"{user_text}\"\n"
                "Mode mock tidak punya LLM sungguhan, tapi saya bisa menjalankan tools.\n"
                f"{help_text}\n"
                "Untuk jawaban AI sungguhan: set LACTION_PROVIDER=openai dan isi LACTION_API_KEY."
            )
        )
