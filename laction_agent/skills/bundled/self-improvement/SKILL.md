---
name: self-improvement
description: Ubah tugas yang berulang menjadi skill baru yang bisa dipakai lagi.
---

# Self-Improvement Loop

Dipakai setelah agent menyelesaikan tugas yang kemungkinan besar muncul lagi.

## Pemicu
- User meminta prosedur yang sama untuk kedua kalinya.
- Urutan tool yang dipakai lebih dari 3 langkah dan stabil.
- Ada kesalahan yang berhasil diperbaiki dan resepnya jelas.

## Langkah
1. Uraikan prosedur: tujuan, urutan tool, input, output, dan jebakan.
2. `create_skill({"name": "nama-skill", "content": "..."})` — nama huruf kecil + strip.
3. `list_skills()` untuk memastikan skill terbaca.
4. `view_skill({"name": "nama-skill"})` untuk verifikasi isi.
5. `memory_save` catatan kapan skill ini sebaiknya dipakai.

## Prinsip
Skill harus prosedural, bukan sekadar catatan fakta. Fakta masuk ke `MEMORY.md`; cara kerja masuk ke `SKILL.md`.
