---
name: reflection
description: Verifikasi hasil dan temukan kekurangan setelah tugas, perubahan kode, atau analisis sebelum memberi jawaban final. Gunakan untuk tugas berisiko atau multi-langkah.
---

# Reflection dan Verifikasi Hasil

1. Bandingkan hasil aktual dengan setiap kriteria yang diminta user.
2. Periksa bukti yang bisa diamati: output tool, file yang ditulis, `git diff --check`, test, atau sumber.
3. Cari efek samping: file tak sengaja berubah, secret dalam output, langkah yang belum dijalankan, dan klaim yang belum didukung.
4. Jika ada kegagalan, perbaiki bila diminta dan aman; jalankan ulang pemeriksaan yang relevan.
5. Sampaikan ringkasan hasil, bukti, keterbatasan, dan next step dengan jujur.

**Privasi reasoning:** berikan kesimpulan, checklist, atau alasan singkat yang dapat diaudit. Jangan tampilkan chain-of-thought internal.