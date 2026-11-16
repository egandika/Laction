---
name: structured-reflexion
description: Catat kegagalan berbasis bukti (gejala, akar masalah, aturan pencegahan) ke MEMORY.md atau skill setelah perbaikan terverifikasi.
---

# Structured Reflexion (Belajar dari Kegagalan Terverifikasi)

Gunakan hanya ketika ada kegagalan nyata (error tool, test gagal, atau penolakan guard) dan perbaikannya sudah teruji.

## Format 3 Bagian
1. **Kegagalan aktual:** perintah/tool yang gagal dan pesan error singkat (tanpa secret).
2. **Akar penyebab terverifikasi:** bukti penyebab dari file, log, atau output tool—bukan tebakan.
3. **Aturan pencegahan:** langkah spesifik agar kesalahan tidak berulang.

## Simpan Secara Tepat
- Pelajaran spesifik proyek/lingkungan -> `memory_save` (ringkas 1–2 baris).
- Prosedur berulang >= 3 langkah yang stabil -> `create_skill` (tetap butuh approval user; jangan menimpa skill yang ada).
- Jangan menyimpan hipotesis yang belum teruji atau mengubah kode sendiri tanpa test dan kontrol manusia.
