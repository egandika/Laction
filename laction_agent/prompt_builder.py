"""Prompt Builder — merakit system prompt dari identitas + memory + skills."""
from __future__ import annotations

from .memory.manager import MemoryManager
from .skills.manager import SkillManager
from .utils import tail

# System prompt tidak pernah dipangkas oleh ContextCompressor, jadi batasnya ada di sini.
MEMORY_LIMIT = 6000
MAX_SKILLS_IN_PROMPT = 40
SKILL_CATALOG_LIMIT = 2600


def _skill_catalog(skill_list: list[dict]) -> str:
    lines: list[str] = []
    omitted = len(skill_list) > MAX_SKILLS_IN_PROMPT
    for skill in skill_list[:MAX_SKILLS_IN_PROMPT]:
        line = f"- {skill['name']}: {skill['description']}"
        candidate = "\n".join([*lines, line])
        if len(candidate) > SKILL_CATALOG_LIMIT:
            omitted = True
            break
        lines.append(line)

    if not lines:
        return "(belum ada skill)"
    if omitted:
        note = "- ... skill lain tidak ditampilkan (pakai list_skills untuk katalog lengkap)"
        while lines and len("\n".join([*lines, note])) > SKILL_CATALOG_LIMIT:
            lines.pop()
        if len(note) <= SKILL_CATALOG_LIMIT:
            lines.append(note)
    return "\n".join(lines)


def build_system_prompt(memory: MemoryManager, skills: SkillManager) -> str:
    skills_text = _skill_catalog(skills.list_skills())
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
- Simpan fakta/pelajaran terverifikasi dengan memory_save, preferensi user dengan user_save.
- Sesuaikan kedalaman: langsung eksekusi tugas sederhana; pecah tugas kompleks & klarifikasi ambiguitas berisiko sebelum aksi besar.
- Jika tool gagal atau ditolak, analisis penyebabnya (Reflexion); jangan mengulang panggilan identik tanpa perubahan.
- Verifikasi klaim penting terhadap file, test, atau hasil tool (CoVe); tandai bagian yang belum diverifikasi alih-alih menebak.
- Jangan tampilkan chain-of-thought internal; berikan rencana ringkas, kesimpulan, dan bukti yang bisa diperiksa.
- Jangan jalankan perintah berbahaya tanpa approval.
- Jawab dalam Bahasa Indonesia kecuali user meminta bahasa lain.
"""
