---
name: git-workflow
description: Periksa perubahan repository, branch, diff, dan riwayat Git; bantu commit atau push hanya sesuai instruksi eksplisit user. Gunakan untuk pekerjaan Git lokal.
---

# Git Workflow Aman

## Inspeksi sebelum perubahan
1. `run_terminal`: `git status --short --branch` dan `git branch --show-current`.
2. Baca diff penuh sebelum mengubah atau commit; cek `git diff --check`.
3. Pastikan hanya file yang dimaksud ikut staging; jangan stage `.env`, database, build, atau data user.
4. Jalankan test yang relevan dan laporkan status branch.

## Perubahan remote
- Buat commit/push/PR hanya bila user meminta atau alur kerja yang sedang berlaku memang menginstruksikannya.
- Jangan force-push, menghapus branch/tag, mengganti branch, atau menimpa perubahan orang lain tanpa izin eksplisit.
- Setelah operasi Git, baca exit code, `git status`, dan hasil remote; jangan menyimpulkan berhasil dari perintah yang baru dikirim.