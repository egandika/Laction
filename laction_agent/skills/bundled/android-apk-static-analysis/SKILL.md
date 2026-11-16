---
name: android-apk-static-analysis
description: Audit APK Android secara statis: baca manifest, permission, DEX strings, URL, dan indikasi secret tanpa menjalankan aplikasi. Gunakan hanya untuk APK milik sendiri atau yang memang berhak diuji.
---

# Android APK Static Triage

## Batas keselamatan
- Pastikan APK diberikan/diotorisasi user. Analisis bersifat lokal dan statis; jangan install atau menjalankan APK.
- `apk_analyze` hanya memindai konten terbatas dan memberi heuristic, bukan bukti bahwa APK aman atau rentan.
- Nilai secret tidak dicetak; catat hanya tipe temuan dan nama entry. Hindari mengirim APK, credential, atau data privat ke layanan web/LLM eksternal.

## Langkah
1. `apk_analyze({"path":"aplikasi.apk"})` untuk metadata, permissions sensitif, flag debuggable/backup/cleartext, exported components, host URL, dan pola credential.
2. Periksa temuan dalam konteks fungsi aplikasi; permission/URL sendiri bukan bukti penyalahgunaan.
3. Untuk satu entry tertentu, gunakan `apk_extract` dengan nama member dan tujuan di workspace. Tool membatasi ukuran dan tidak menjalankan `extract-all`.
4. Untuk dekompilasi lengkap, gunakan `jadx`/`apktool` hanya bila sudah tersedia dan user mengizinkan. Built-in tool tidak mendekompilasi Smali atau resource table penuh.
5. Buat laporan: ringkasan, bukti (entry/komponen), severity, confidence, false-positive caveat, dan rekomendasi aman.

Analisis dinamis dengan emulator, Frida, atau Logcat **tidak didukung** oleh built-in agent ini; perlu lab terisolasi dan izin khusus.