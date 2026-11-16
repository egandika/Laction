---
name: release-notes
description: Susun catatan rilis dari riwayat git dan diff perubahan.
---

# Release Notes

## Langkah
1. `run_terminal({"command": "git log --oneline -15"})`.
2. `run_terminal({"command": "git describe --tags --always"})` untuk penanda versi.
3. `run_terminal({"command": "git diff <tag-sebelumnya>..HEAD --stat"})` bila tag tersedia.
4. Kelompokkan perubahan: **Fitur**, **Perbaikan**, **Dokumentasi**, **Breaking change**.
5. Tulis ke `CHANGELOG.md` dengan `write_file` (baca dulu bila file sudah ada).
6. Simpan ringkasan rilis ke `MEMORY.md` lewat `memory_save`.

## Gaya
Bahasa Indonesia, kalimat imperatif ringkas, tanpa jargon berlebih. Sertakan cara upgrade bila ada breaking change.
