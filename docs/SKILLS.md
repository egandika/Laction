# Analisis & keputusan daftar skill Laction

Tanggal riset: **16 November 2026**. Tujuan bukan menyalin semua label menjadi fitur palsu, melainkan memilih kemampuan yang cocok dengan batas desain Laction: Python 3.11+, stdlib-only, local-first, mock tanpa API key, dan tindakan berisiko harus dibatasi.

## Ringkasan keputusan

- **Sudah ada:** tool calling, loop ReAct, memory jangka pendek/panjang, multi-step tool loop, shell/file, cron, catatan, web fetch, OpenRouter/OpenAI-compatible, sub-agent, dan procedural skills.
- **Ditambahkan:** 5 tools (`run_python`, `web_search`, `rag_search`, `apk_analyze`, `apk_extract`), provider alias Gemini, 9 procedural skills, serta aturan prompt planning/verifikasi.
- **Tidak diimplementasikan sekarang:** MCP client/server, bot Telegram/WhatsApp, Android dynamic analysis (Frida/Logcat), vector embeddings, YouTube transcript, image/audio tools. Keputusan dan batasnya ada di tabel bawah.

## Pemetaan permintaan

| Kelompok | Status | Implementasi / alasan |
|---|---|---|
| Tool calling, ReAct, multi-step | Sudah ada | `AIAgent.run()` mengulang `provider.chat → tool → observation` hingga selesai atau mencapai `max_iterations`. Ini sejalan dengan pola ReAct yang menggabungkan reasoning dan action secara bergantian [1](https://arxiv.org/abs/2210.03629). |
| Planning & reflection | Ditambah sebagai skill + aturan system prompt | `planning` memecah tugas; `reflection` memeriksa hasil yang dapat diamati. Tidak meminta model membuka chain-of-thought privat; jawaban memberi kesimpulan, checklist, dan bukti. |
| Short/long-term memory | Sudah ada | Riwayat turn di SQLite, fakta/preferensi di `MEMORY.md`/`USER.md`, prosedur di `SKILL.md`. FTS5 dan vector store belum ada. |
| Python runner / debugger | Ditambah | `run_python` menjalankan potongan Python tanpa shell, timeout 1–30 detik, **approval eksplisit selalu**. Ini tetap arbitrary code dengan hak OS user—bukan sandbox; gateway/one-shot tanpa approval tidak mengeksekusi. |
| Shell, file, Git, Termux | Sudah ada + skill | `run_terminal` dan file tools bekerja lokal; `git-workflow` menjelaskan inspeksi dan guard. Termux adalah lingkungan eksekusi, bukan backend khusus. `run_terminal` tetap `shell=True` dan bukan sandbox. |
| Web scraper / reader | Sudah ada | `web_fetch` mengambil halaman HTTP(S) publik; guard SSRF menolak alamat private. |
| Web search / OSINT publik | Ditambah, terbatas | `web_search` mengurai hasil HTML DuckDuckGo tanpa dependency/API key; endpoint ini tidak resmi, bisa berubah/rate-limit, dan **query dikirim ke DuckDuckGo** [2](https://bestscraperapi.com/guides/how-to-scrape-duckduckgo). `public-web-research` mewajibkan sumber publik, verifikasi halaman, serta larangan doxxing/credential collection. Bukan Google/Brave API. |
| APK extractor, manifest, permission, DEX string, secret scan, laporan statis | Ditambah | `apk_analyze` membaca APK ZIP, text/binary Android XML (AXML), permission, exported components, flag app, URL host dan pola credential; secret value tidak dicetak. `apk_extract` menulis satu entry pilihan ke workspace dengan batas ukuran/path. Tidak install atau menjalankan APK. |
| Smali/jadx/apktool | Terbatas | Raw entry bisa diekstrak; dekompilasi penuh perlu `jadx`/`apktool` yang dipasang terpisah. Tidak ada decompiler bawaan. |
| Android dynamic analysis | Ditunda | Frida/Logcat memerlukan device/emulator/lab terisolasi dan izin; tidak cocok dijalankan otomatis dari agent local-first generik. |
| Scheduler, notes, translator, summarizer | Sebagian sudah ada | Cron interval dan memory notes sudah tersedia; `productivity-workflows` mengatur penggunaan/ekspektasi. Translator/summarizer memerlukan LLM sungguhan; mock hanya menguji flow, bukan kualitas bahasa. Cron belum menjadi push notification atau job sekali-jalan. |
| RAG / vector memory | Ditambah sebagian | `rag_search` melakukan ranking **BM25 leksikal** pada file teks workspace, hasil berisi path:baris; batas ukuran dan folder sensitif dikecualikan. BM25 adalah retrieval kata kunci (lihat [3](https://ngpestelos.com/reference/bm25/)), **bukan** semantic/vector embeddings. Embedding memerlukan model/API atau dependency/storage tambahan. |
| OpenRouter / Gemini API | Ditambah Gemini | OpenRouter sudah ada. Provider `gemini` baru menggunakan endpoint OpenAI-compatible resmi Google dan function calling [4](https://ai.google.dev/gemini-api/docs/openai). Model/key tetap milik user; fitur khusus Gemini di luar Chat Completions tidak otomatis tersedia. |
| Telegram / WhatsApp bot | Ditunda | Memerlukan bot token, webhook/polling, penyimpanan secret, persetujuan penerima, dan batas pengiriman eksternal. Tidak aman menganggap messaging sebagai tool tanpa kebijakan consent. |
| Image analyzer/generator, speech-to-text/text-to-speech, YouTube summarizer | Ditunda | Interface provider saat ini menerima teks; belum ada media/transcript pipeline atau file lifecycle untuk fitur tersebut. Mengaku mampu tanpa jalur multimodal yang diuji akan menyesatkan. |
| MCP Filesystem/Termux/GitHub/Brave/Telegram/Memory | Ditunda | Tool lokal Laction bukan MCP client. MCP memakai JSON-RPC dan transport stdio atau Streamable HTTP; client harus mengelola proses, framing, discovery, validasi schema, permission, dan trust boundary [5](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) [6](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture). Implementasi parsial yang langsung mengeksekusi server eksternal tidak aman; MCP tetap roadmap. |

## Fitur baru dan guard teknis

### `run_python`

- Jalankan `sys.executable -B -c <code>` tanpa `shell=True`, timeout paling lama 30 detik.
- Selalu meminta callback approval; tanpa approval atau pada `approval_mode=never`, kode tidak berjalan.
- **Tidak diisolasi dari filesystem/network/OS.** Persetujuan hanya memberi kontrol user, bukan sandbox. Jangan jalankan kode tidak tepercaya; backend Docker masih prioritas sebelum penggunaan LLM produksi.

### `web_search`

- Hanya mengirim query ke endpoint tetap `html.duckduckgo.com`; query yang cocok dengan pola credential umum ditolak, tool tidak membuat URL fetch bebas, dan hasil tidak dikunjungi otomatis.
- Parser stdlib membatasi respons 1 MB dan jumlah hasil; redirect DuckDuckGo diurai hanya untuk menghasilkan tautan `http(s)`.
- CAPTCHA, challenge, rate-limit, perubahan markup, atau jaringan mati dikembalikan sebagai pesan keterbatasan—bukan disamarkan sebagai hasil kosong yang valid.
- Pencarian bukan privat: jangan masukkan token, data user, atau identifier yang tidak perlu. Gunakan `web_fetch` untuk membaca sumber yang dipilih.

### `rag_search`

- BM25 dihitung lokal, per query, tanpa vector DB / embedding / jaringan.
- Hanya file teks yang diizinkan, maksimum 300 file / 8 MiB konten / 2.500 chunk; mengecualikan `.git`, hidden folders, `data/`, virtualenv, dan folder build.
- Path dijaga tetap di dalam workspace; output menampilkan path dan rentang baris agar model dapat mengutip sumber.
- Konten output melewati redaksi secret yang tersedia; redaksi heuristik bukan jaminan anonimisasi.

### `apk_analyze` dan `apk_extract`

- Sumber harus file `.apk` di workspace; ZIP dibatasi 200 MiB dan 25.000 entries.
- AXML parser membaca string pool dan start-element attributes untuk manifest; parsing dapat gagal pada varian malformed/unsupported, jadi hasil bukan pengganti AAPT2/apktool.
- Scan DEX/teks dibatasi total 64 MiB; secret dilaporkan sebagai **jenis + entry** tanpa nilai; tidak ada dynamic execution.
- `apk_extract` hanya membaca satu entry dan menulis ke tujuan yang lolos workspace guard, maksimum 64 MiB; tidak memakai `extractall` sehingga nama entry tidak dapat melakukan zip-slip.
- Analisis hanya untuk APK yang user miliki/berhak audit. Heuristic bisa false positive/negative; report menyatakan keterbatasan.

## Skill bawaan baru

Format tiap folder mengikuti Agent Skills: folder + `SKILL.md`, `name` dan `description` frontmatter; metadata ringkas masuk katalog dan isi dimuat lewat `view_skill` saat dibutuhkan (*progressive disclosure*) [7](https://agentskills.io/specification).

1. `planning`
2. `reflection`
3. `python-debugging`
4. `git-workflow`
5. `android-apk-static-analysis`
6. `local-rag`
7. `public-web-research`
8. `provider-setup`
9. `productivity-workflows`

Empat skill lama (`repo-onboarding`, `code-review`, `release-notes`, `self-improvement`) tetap ada. Test memeriksa 13 folder, nama/frontmatter, deskripsi, dan batas panjang.

## Verifikasi yang ditambahkan

`tests/test_added_capabilities.py` menguji approval Python, retrieval + redaksi/path guard, parsing hasil DDG tanpa jaringan, konfigurasi provider Gemini, APK manifest teks dan binary AXML, penemuan permission/flag/secret tanpa mencetak nilai, ekstraksi satu entry, zip-slip guard, serta bentuk frontmatter skill. Semua komponen tetap memakai Python stdlib.

## Referensi riset

- [1] Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, arXiv:2210.03629.
- [2] Catatan teknis endpoint HTML DuckDuckGo: tidak ada kontrak API organik resmi; endpoint dapat membatasi scraping.
- [3] Ringkasan formulasi/ranking Okapi BM25 dan rujukan Robertson et al., *Okapi at TREC-3*.
- [4] Dokumentasi Google Gemini API: OpenAI compatibility dan function calling.
- [5] Dokumentasi transport resmi MCP, stdio dan Streamable HTTP.
- [6] Dokumentasi arsitektur resmi MCP.
- [7] Spesifikasi resmi Agent Skills.
- Android: [APK sebagai ZIP + manifest binary XML](https://developer.android.com/topic/performance/reduce-apk-size), [AAPT2 manifest/permission tools](https://developer.android.com/tools/aapt2).
