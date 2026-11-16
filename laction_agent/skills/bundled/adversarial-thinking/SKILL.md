---
name: adversarial-thinking
description: Devil's Advocate, Inversion, First Principles, dan klarifikasi Socratic untuk menguji keputusan atau rancangan berisiko.
---

# Adversarial Thinking & First Principles

Gunakan sebelum mengambil keputusan arsitektur, keamanan, atau aksi yang sulit dibatalkan.

## Teknik Inti
1. **First Principles:** pisahkan fakta terukur (`read_file`, `device_health`) dari asumsi; bangun opsi dari batas nyata, bukan analogi permukaan.
2. **Inversion (Anti-Goal):** tanyakan *"bagaimana cara rencana ini gagal total atau membahayakan data?"*, lalu buat mitigasi untuk setiap titik gagal utama.
3. **Devil's Advocate:** cari minimal 3 alasan kuat mengapa solusi pilihan bisa salah, rapuh, atau melebihi batas resource. Untuk evaluasi baca-saja dua sisi, pertimbangkan `consult_team(task=..., mode="debate")`.
4. **Klarifikasi Socratic (maks 3 pertanyaan):** jika permintaan ambigu dan kesalahan asumsi mahal atau sulit dibalik, ajukan pertanyaan singkat sebelum mengeksekusi aksi.

## Batasan
- Mode debat hanya 1 putaran dan read-only; jangan berdebat berulang-ulang tanpa bukti baru.
- Jangan menunda tugas sederhana yang sudah jelas dan aman dengan pertanyaan yang tidak perlu.
