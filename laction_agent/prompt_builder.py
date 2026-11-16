"""Prompt Builder — merakit system prompt dari identitas + memory + skills."""
from __future__ import annotations

from .memory.manager import MemoryManager
from .skills.manager import SkillManager
from .utils import tail

# System prompt tidak pernah dipangkas oleh ContextCompressor, jadi harus
# dibatasi di sini. MEMORY.md bersifat append-only → simpan bagian TERBARU.
MEMORY_LIMIT = 6000
MAX_SKILLS_IN_PROMPT = 40


def build_system_prompt(memory: MemoryManager, skills: SkillManager) -> str:
    skill_list = skills.list_skills()
    shown = skill_list[:MAX_SKILLS_IN_PROMPT]
    skills_text = "\n".join(f"- {s['name']}: {s['description']}" for s in shown) or "(belum ada skill)"
    if len(skill_list) > MAX_SKILLS_IN_PROMPT:
        skills_text += (
            f"\n- ... {len(skill_list) - MAX_SKILLS_IN_PROMPT} skill lain "
            "(pakai list_skills untuk daftar lengkap)"
        )
    memory_text = tail(memory.read_all(), MEMORY_LIMIT)

    return f"""Kamu adalah Laction Agent — AI agent lokal yang membantu user di repo Laction.
Bahasa: ikuti bahasa user (default Bahasa Indonesia).
Gaya: ringkas, jelas, langsung ke solusi. Gunakan tools bila perlu, jangan menebak isi file.

--- MEMORY (ingat antar sesi, bagian terbaru) ---
{memory_text}

--- SKILLS TERSEDIA ---
{skills_text}
Gunakan view_skill untuk melihat detail skill sebelum memakainya.
Setelah menyelesaikan tugas kompleks yang berulang, pertimbangkan membuat skill baru dengan create_skill.

Aturan:
- Simpan fakta penting dengan memory_save, preferensi user dengan user_save.
- Jangan jalankan perintah berbahaya tanpa approval.
- Jawab dalam Bahasa Indonesia kecuali user meminta bahasa lain.
"""
