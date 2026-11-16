---
name: python-debugging
description: Reproduksi bug Python, baca traceback, uji hipotesis, dan validasi perbaikan dengan runner atau unittest. Gunakan saat debugging kode Python.
---

# Python Debugging

1. Baca file dan test yang terkait; jangan menebak isi kode.
2. Dapatkan reproduksi minimal: jalankan test yang gagal atau skrip kecil.
3. `run_python` hanya tersedia dengan persetujuan eksplisit di sesi interaktif. Tinjau kode yang akan dijalankan; runner ini **bukan sandbox**.
4. Untuk test proyek gunakan `run_terminal` seperti `python -m unittest discover -s tests -v`; periksa exit code dan traceback.
5. Temukan akar masalah, lakukan patch sekecil mungkin, lalu jalankan test regresi dan test terkait.
6. Laporkan penyebab, perubahan, dan hasil validasi; jangan menyembunyikan test yang masih gagal.

Jangan mengirim isi `.env`, token, data user, atau file privat ke layanan eksternal.