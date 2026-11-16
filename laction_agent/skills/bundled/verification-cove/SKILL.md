---
name: verification-cove
description: Chain-of-Verification (CoVe) dan fact-check berbasis bukti tool untuk menekan halusinasi sebelum jawaban final.
---

# Chain-of-Verification (CoVe) & Grounded Fact-Check

Gunakan untuk klaim faktual, audit kode/APK, atau jawaban berisiko tinggi agar tidak mengulang kesalahan draf awal.

## 4 Langkah CoVe
1. **Draf klaim utama:** identifikasi fakta, perilaku kode, nama simbol, atau risiko yang ingin disampaikan.
2. **Buat 2–4 pertanyaan verifikasi independen:** fokus pada detail yang paling mungkin salah (path file, fungsi, config, angka, klaim keamanan).
3. **Verifikasi langsung memakai tool (bukan ingatan):** jalankan `read_file`, `search_files`, `rag_search`, `apk_analyze`, `web_fetch`, atau test yang relevan untuk setiap pertanyaan secara terpisah dari asumsi awal.
4. **Revisi jawaban final:** pertahankan hanya klaim yang didukung bukti.

## Aturan Pelabelan
- Tandai `[TERVERIFIKASI: sumber]` jika baru saja dibaca dari tool/test.
- Tandai `[BELUM DIVERIFIKASI]` atau `[ASUMSI]` jika belum ada bukti langsung.
- Jangan mengarang skor keyakinan 1–100 tanpa dasar terukur; jelaskan ketidakpastian dan bukti yang kurang secara konkret.
