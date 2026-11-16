---
name: planning
description: Plan pekerjaan kompleks menjadi langkah kecil yang dapat diverifikasi, pilih tools yang tepat, dan atur tugas multi-langkah. Gunakan saat permintaan punya beberapa hasil atau dependensi.
---

# Planning untuk Tugas Multi-Langkah

## Cara kerja
1. Ringkas tujuan akhir dan batasan eksplisit user dalam satu kalimat.
2. Pecah menjadi 3–7 langkah berurutan; tandai langkah yang bisa dikerjakan paralel.
3. Baca file/sumber sebelum menyimpulkan. Pilih tool paling sempit yang cukup.
4. Jalankan satu langkah, amati hasilnya, lalu sesuaikan rencana bila bukti berubah (ReAct), bukan mengeksekusi rencana buta.
5. Setelah perubahan, verifikasi acceptance criteria dengan test, diff, atau sumber yang relevan.
6. Laporkan hasil, bukti verifikasi, dan hal yang belum dilakukan.

## Aturan
- Tampilkan rencana ringkas bila membantu; jangan mengeluarkan chain-of-thought internal.
- Jangan mengklaim tool berhasil sebelum membaca hasilnya.
- Hindari aksi irreversible atau eksternal tanpa permintaan/persetujuan yang jelas.
- Gunakan `delegate_task` hanya untuk pekerjaan yang mandiri dan tidak berbagi state mutable.