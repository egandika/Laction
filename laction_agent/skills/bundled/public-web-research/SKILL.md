---
name: public-web-research
description: Cari dan rangkum informasi web publik dari sumber yang dapat diperiksa, bedakan fakta dan inferensi, serta cantumkan tautan. Gunakan untuk riset yang membutuhkan informasi terbaru.
---

# Riset Web Publik

1. Sebelum mencari, hapus credential, data privat, dan identifier personal yang tidak perlu dari query.
2. `web_search` mengirim query ke DuckDuckGo; endpoint HTML best-effort dapat dibatasi atau berubah.
3. Buka sumber relevan dengan `web_fetch` dan prioritaskan dokumentasi resmi atau sumber primer.
4. Beri tautan, tanggal bila tersedia, dan bedakan kutipan/fakta dari inferensi. Jangan mengandalkan satu snippet pencarian.
5. Untuk OSINT, batasi pada informasi publik yang relevan dan tidak sensitif; jangan melakukan doxxing, melacak orang privat, atau mengumpulkan credential.

`web_fetch` menolak alamat privat secara default. `web_search` bukan layanan Google/Brave, tidak menjamin hasil lengkap, dan memerlukan koneksi internet.