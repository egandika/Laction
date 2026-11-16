---
name: local-rag
description: Jawab pertanyaan berdasarkan file teks di workspace dengan retrieval lokal dan kutipan path/baris. Gunakan untuk repository atau dokumen milik user.
---

# Local RAG

1. Cari bukti dengan `rag_search({"query":"...", "path":".", "limit":5})`.
2. Gunakan potongan dan referensi path:baris yang dikembalikan sebagai sumber; buka file via `read_file` bila perlu konteks lebih luas.
3. Sintesis jawaban hanya dari bukti yang ditemukan. Jika tidak ada hasil, katakan demikian atau persempit query.
4. Cantumkan sumber file di jawaban agar dapat dicek user.

Retrieval saat ini **BM25 leksikal**, bukan vector database atau semantic embeddings. Ia mengindeks terbatas file teks non-hidden, mengecualikan `data/`, `.git`, virtualenv, dan build; hasil bisa tidak lengkap. Jangan menganggap hasil retrieval sebagai kebenaran tanpa membaca konteks.