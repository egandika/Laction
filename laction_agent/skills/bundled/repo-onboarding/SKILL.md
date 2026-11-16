---
name: repo-onboarding
description: Peta cepat isi repo Laction sebelum mengerjakan tugas apa pun.
---

# Repo Onboarding

Gunakan skill ini saat pertama kali masuk ke repo atau saat struktur proyek terasa asing.

## Langkah
1. `list_files({"path": "."})` untuk melihat kerangka direktori.
2. Baca `README.md`, lalu `pyproject.toml` / `package.json` bila ada.
3. `search_files` untuk kata kunci: `TODO`, `FIXME`, `main`, `Config`, `AIAgent`.
4. `read_file` pada 2–3 modul inti (di Laction: `laction_agent/agent.py`, `laction_agent/cli.py`, `laction_agent/tools/registry.py`).
5. Simpan temuan penting dengan `memory_save`, misalnya: "Entry point ada di laction_agent/cli.py".
6. Baru kerjakan tugas user. Jangan menebak isi file — selalu baca dulu.

## Keluaran
Ringkasan 5–8 baris: tujuan repo, entry point, modul inti, cara test, dan catatan risiko.
