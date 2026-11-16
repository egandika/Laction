---
name: code-review
description: Review perubahan kode secara lokal sebelum commit atau pull request.
---

# Code Review Lokal

## Langkah
1. `run_terminal({"command": "git status --short"})` lalu `git diff --stat`.
2. Baca diff lengkap: `git diff` (atau `git diff --cached`).
3. Untuk tiap file berubah, `read_file` dan cek:
   - error handling & tipe data,
   - path traversal / input user,
   - secret yang tanpa sengaja ikut,
   - konsistensi nama & docstring.
4. `search_files` untuk `TODO`, `print(`, `except Exception`, `shell=True`.
5. Jalankan test: `python3 -m pytest -q` (fallback `python3 -m unittest discover -s tests -v`).
6. Laporkan temuan dengan format: **[blocker]**, **[saran]**, **[oke]**.

## Aturan
Jangan mengubah kode tanpa diminta. Kalau diminta perbaiki, lakukan perubahan kecil dan jalankan test ulang.
