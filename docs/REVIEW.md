# Review Laction Agent v0.1 → v0.1.1

**Tanggal:** 2026-11-16 · **Branch:** `arena/24815512-laction` · **Basis:** `3c1bab5d` (PR #1)
**Metode:** baca seluruh modul (≈2.500 baris), jalankan probe eksplisit untuk mencari bypass, jalankan 47 test, cek wheel/CI/gateway, lalu perbaiki temuan dan tulis regresi test.

---

## 1. Verdict singkat

| Aspek | Nilai | Catatan |
|---|---|---|
| Arsitektur | **Baik** | Pemisahan provider / loop / tools / memory / skill bersih dan mudah diganti |
| Kebenaran loop | **Baik** | Tool-calling loop, kompresi menjaga pasangan tool call/result, ada batas iterasi |
| Kemudahan pakai | **Sangat baik** | Mode `mock` benar-benar menjalankan tools tanpa API key |
| Keamanan | **Awalnya lemah → diperbaiki** | 3 celah nyata (terminal bypass, SSRF, kebocoran secret) |
| Robustness | **Cukup → diperbaiki** | Cron fire-on-start & blocking, kompresi yang terlewat, system prompt tanpa batas |
| Dokumentasi & test | **Baik** | README + ARCHITECTURE + CI 3 versi Python; sekarang 47 test |

**Kesimpulan:** fondasi agentnya sehat dan layak dipakai untuk eksperimen lokal. Yang bermasalah bukan idenya, melainkan **detail implementasi di lapisan keamanan dan batas konteks**. Sembilan temuan di bawah sudah diperbaiki; sisanya (§6) adalah batasan desain yang sengaja didokumentasikan, bukan bug yang disembunyikan.

---

## 2. Penjelasan: apa sebenarnya "AI agent" ini?

Hermes Agent itu **bukan model**. Dia *harness*: program yang mengelola percakapan, memori, dan eksekusi di sekeliling model. Jadi Laction Agent juga bukan LLM — dia **loop orkestrator** yang bisa memakai LLM apa pun.

Analogi sederhana:

```text
LLM  = otak yang menjawab "langkah apa selanjutnya?"
Agent = tangan + ingatan + aturan yang benar-benar menjalankan langkah itu
```

### Satu turn, dari ketikan sampai jawaban

```text
user: "baca file README.md"
  │
  ├─ cli.py / gateway.py  → Config.load()  (env > .env > config.yaml > default)
  ├─ AIAgent.__init__     → MemoryManager, SkillManager, SessionDB, Provider
  ├─ PromptBuilder        → system prompt = identitas + MEMORY.md + USER.md + daftar SKILL.md
  ├─ agent.run()          → tambah Message(user), simpan ke SQLite
  │
  ├─ 🔁 LOOP (maks max_iterations):
  │    1. ContextCompressor.compress()  → ringkas riwayat bila > context_limit
  │    2. Provider.chat(history, tools)→ ProviderResponse(teks | tool_calls)
  │    3. tanpa tool_calls → selesai, kembalikan teks
  │    4. ada tool_calls   → ToolRegistry.call() untuk tiap call
  │                         → hasil jadi Message(role="tool", tool_call_id=...)
  │                         → ulangi dari (1) supaya LLM melihat hasilnya
  │
  └─ simpan jawaban, cetak / kirim JSON
```

Dua hal yang bikin ini "agent" bukan sekadar chatbot:

1. **Tool feedback loop** — hasil eksekusi dikembalikan ke model sebagai observasi, sehingga model bisa memutus langkah berikutnya.
2. **State yang bertahan** — `MEMORY.md`, `USER.md`, `sessions.db`, dan `SKILL.md` hidup di `LACTION_HOME`; sesi berikutnya memuatnya lagi lewat system prompt. Itu *closed learning loop*: pengalaman → catatan/skill → muncul di prompt → dipakai lagi.

### Peta modul (6 layer Hermes)

| Layer | File | Peran |
|---|---|---|
| Surface | `cli.py`, `gateway.py` | REPL / one-shot / HTTP + UI chat |
| Session | `config.py`, `memory/session_db.py` | profil `LACTION_HOME`, riwayat SQLite |
| Reasoning | `providers/` | `MockProvider`, `OpenAICompatProvider` (satu kontrak `chat()`) |
| Memory | `memory/`, `prompt_builder.py` | Markdown yang selalu hadir + pencarian sesi |
| Skill | `skills/` | `SKILL.md` prosedural, 4 bawaan + buatan agent |
| Execution | `tools/` | 20 tool self-registering via `@reg.register` |

Yang paling elegan: **tool tidak tahu apa-apa soal `AIAgent`**. `ToolRegistry.call()` menyuntik `context` (memory, skills, db, cron, approve, delegate). Jadi menambah tool = satu fungsi + skema JSON; `agent.py` tidak berubah.

---

## 3. Yang sudah bagus (tidak diubah)

- **Zero dependency** benar-benar tercapai: hanya `urllib`, `sqlite3`, `http.server`, `argparse`, `subprocess`, `threading`.
- **Provider abstraction** rapi. Ganti OpenAI → Ollama cuma ganti env; skema tool tetap format OpenAI function calling.
- **`ContextCompressor`** punya ide yang benar: system prompt dilindungi, satu turn terakhir dipertahankan utuh supaya pesan `assistant(tool_calls)` tidak kehilangan pasangan `tool`-nya (kalau tidak, API OpenAI-compatible menolak request).
- **Tool error → observasi**, bukan crash: exception dibungkus jadi string `{"error": ...}`.
- **Path guard** `resolve()` menolak `../` dan path absolut keluar workspace, termasuk symlink.
- **`MockProvider`** cerdas: setelah tool result ia berhenti memanggil tool lagi dan merangkai jawaban. Tanpa ini loop mock akan tak berujung.
- **CLI** lengkap (one-shot, REPL, status, tools, skills, memory, cron, doctor, gateway) dan URL UI gateway relatif semua, aman di balik proxy preview.

---

## 4. Temuan & perbaikan

| ID | Severitas | Temuan | Status |
|---|---|---|---|
| F-01 | 🔴 Blocker | Bypass daftar perintah berbahaya | ✅ diperbaiki |
| F-02 | 🔴 Blocker | SSRF lewat `web_fetch` | ✅ diperbaiki |
| F-03 | 🟠 High | Redaksi secret lemah + riwayat plaintext | ✅ diperbaiki |
| F-04 | 🟡 Medium | Cron fire-on-start & blocking | ✅ diperbaiki |
| F-05 | 🟡 Medium | Kompresi terlewat untuk ≤6 pesan besar | ✅ diperbaiki |
| F-06 | 🟡 Medium | System prompt tanpa batas | ✅ diperbaiki |
| F-07 | 🔵 Low | `list file -la` jadi shell command invalid | ✅ diperbaiki |
| F-08 | 🔵 Low | Warning config tidak akurat | ✅ diperbaiki |
| F-09 | 🔵 Low | License classifier deprecated | ✅ diperbaiki |

### F-01 — Bypass proteksi terminal 🔴

**Bukti (probe sebelum perbaikan):**

```text
dangerous=False  echo $(curl https://evil.example)
dangerous=False  echo `rm -rf /tmp/x`
dangerous=False  printf 'x' > a; dd if=/dev/zero of=/dev/sda
```

**Penyebab:** pengecekan lama `f" {d} " in " {cmd} " or cmd.startswith(d)`. Pola `"dd "` berubah jadi `" dd  "` (spasi ganda) sehingga tidak pernah cocok, dan `$(...)`/backtick menyembunyikan perintah di dalam argumen.

**Dampak:** pada `approval_mode=never`, perintah berbahaya yang dirangkai bisa lolos dan dieksekusi `shell=True`.

**Perbaikan:** `terminal_tool.py` memakai regex ber-boundary atas seluruh string + flag eksplisit untuk `$(` dan backtick; daftar diperluas (`rm -fr`, `dd if=`, `git push -f`, `>/dev/sd`, ...). Perintah aman (`ls -la`, `echo halting`, `Mask-abcdefgh`) tetap tidak terflag.

### F-02 — SSRF di `web_fetch` 🔴

**Sebelumnya:** URL apa pun diterima, termasuk `http://169.254.169.254/latest/meta-data/` (cloud credentials), `localhost`, `10.x`. Karena tool ini dipanggil atas keputusan LLM, ini kanal eksfiltrasi klasik.

**Perbaikan:** `web_tools.py` menolak loopback/private/link-local/reserved, `localhost`, dan sufiks `.local`/`.internal` (termasuk hasil DNS). Opt-out eksplisit `LACTION_ALLOW_PRIVATE_WEB=1` untuk dev lokal. `doctor` ikut mengecek guard ini.

### F-03 — Kebocoran kredensial 🟠

**Tiga jalur bocor:**

1. `redact()` cuma kenal `sk-*` dan `ghp_*` → `github_pat_`, `xoxb-`, `AIza...`, `Bearer ...`, `api_key=...` lolos ke log.
2. `agent.py` menyimpan **hasil tool apa adanya** ke SQLite → `cat .env` / `env` / respons API ber-secret bisa muncul lagi lewat `memory_search` dan `GET /history`.
3. `memory_save` / `user_save` menulis ke Markdown yang **selalu disuntik ke system prompt** → secret terkirim ke provider.

**Perbaikan:** pola redaksi diperluas (token umum + Bearer + `key=value`); `_persist()` menyamarkan semua tulisan DB; `memory_save`, `user_save`, `create_skill` ikut menyamarkan. `redact()` dijamin tidak mengubah teks biasa.

### F-04 — Cron: fire-on-start & blocking 🟡

`_last_run.get(name, 0)` membuat `now - 0 >= interval` selalu true → **semua job langsung jalan saat start**, walaupun intervalnya 3600 detik. Selain itu `on_run()` dipanggil sinkron di thread scheduler, jadi satu tugas lambat menghentikan semua job lain.

**Perbaikan:** `_last_run` diisi saat `add_job` / `start`; tiap job jalan di thread daemon dengan flag in-flight (anti duplikat); file `cron.json` korup tidak lagi mematikan thread.

### F-05 — Kompresi terlewat 🟡

```python
if estimate_tokens(messages) <= limit or len(messages) <= 6:
    return messages   # ❌
```

Lima pesan berisi tool result 8.000 karakter = ~6.000 token, tapi tetap 5 pesan → dilewatkan tanpa kompresi. **Perbaikan:** shortcut aman diturunkan jadi `len(messages) <= 3` (system + user + satu balasan memang tak ada yang bisa diringkas). Probe: 6.000 → 604 token.

### F-06 — System prompt tanpa batas 🟡

`compress()` **sengaja tidak pernah memangkas** system prompt. Karena `MEMORY.md` append-only dan disuntik penuh, pertumbuhan memori = pertumbuhan konteks tanpa batas.

**Perbaikan:** `prompt_builder.py` membatasi memori 6.000 karakter dengan `tail()` (menyimpan catatan **terbaru**) dan daftar skill maks 40 entri + penunjuk `list_skills`.

### F-07 / F-08 / F-09 — Kecil tapi nyata 🔵

- `list file -la` diterjemahkan jadi perintah shell `"list file -la"` (tidak ada) → dinormalisasi ke `ls -la`.
- Warning `approval_mode=never` bilang "menonaktifkan proteksi", padahal perintah berbahaya **tetap diblokir**; warning Ollama-localhost tidak muncul saat `api_base` kosong (padahal defaultnya localhost). Keduanya dibetulkan.
- Metadata lisensi memakai bentuk lama (`license = {text = "MIT"}` + classifier `License :: ...`) yang memicu **6 warning deprecation** setiap build di setuptools ≥77, dan akan berhenti didukung Februari 2027. **Perbaikan penuh:** migrasi ke PEP 639 — `license = "MIT"`, `license-files = ["LICENSE"]`, classifier dihapus, `build-system.requires` dinaikkan ke `setuptools>=77`. Hasil build wheel sekarang **0 warning** dan METADATA memuat `License-Expression: MIT` + `License-File: LICENSE`. Konsekuensi: `pip install --no-build-isolation` membutuhkan setuptools ≥77 (instalasi normal dengan build isolation tetap otomatis).

---

## 5. Cara verifikasi perbaikan

```bash
python3 -m compileall -q laction_agent tests
python3 -m unittest discover -s tests -v     # 47 test, OK
python3 -m laction_agent doctor               # 10 check, termasuk 3 guard keamanan
```

Regresi ada di `tests/test_review_fixes.py` (21 test). `doctor` sekarang menampilkan:

```text
✅ Redaksi secret    token & key=value tersamarkan
✅ Terminal guard    chain & substitusi terdeteksi
✅ SSRF guard        privat/link-local diblokir
```

CI (`.github/workflows/ci.yml`) otomatis menjalankan semua ini di Python 3.11 / 3.12 / 3.13 untuk tiap push & PR.

---

## 6. Risiko residual (jujur, belum diperbaiki)

| Risiko | Kenapa belum | Rekomendasi |
|---|---|---|
| `run_terminal` masih `shell=True` + *denylist*, bukan sandbox | Butuh runtime eksternal, melanggar prinsip zero-dependency | `DockerExecutor` / allowlist perintah untuk produksi |
| `WORKSPACE = Path.cwd()` di-capture saat import | Desainnya memang "cwd = workspace"; mengubahnya butuh plumbing config ke semua tool | Tambah `LACTION_WORKSPACE` eksplisit |
| `redact()` bersifat heuristik | Tidak ada cara generik menjamin semua format token | Jangan simpan secret di memori; pakai secret manager |
| `write_file` sengaja **tidak** di-redact | Menyamarkan isi file akan merusak hasil tulis | Edukasi: jangan minta agent menulis kredensial ke repo |
| `web_fetch` cek DNS tanpa timeout khusus | `getaddrinfo` memakai resolver sistem | Batasi dengan timeout / resolver sendiri |
| `memory_search` pakai `LIKE`, bukan FTS5 | FTS5 butuh skema tambahan | Migrasi ke FTS5 + ranking |
| Gateway: CORS `*`, tanpa TLS/rate-limit/multi-user | Di luar scope v0.1 | Reverse proxy + token + rate limit sebelum ekspos |
| Belum ada MCP, DSPy/GEPA, sub-agent paralel | Inti sengaja kecil | Lihat roadmap README §10 |

Catatan penting: **`MockProvider` bukan LLM**. Ia memetakan perintah Bahasa Indonesia ke tool call dan merangkai jawaban template. Gunanya menguji *harness*-nya, bukan kualitas penalaran. Untuk penalaran sungguhan wajib `LACTION_PROVIDER=openai` (atau setara) + API key.

---

## 7. Rekomendasi urutan lanjutan

1. **Sandbox eksekusi** — prioritas tertinggi kalau agent akan dipakai dengan LLM sungguhan yang bisa salah memilih perintah.
2. **FTS5 + batas ukuran `MEMORY.md` di level file** (bukan cuma saat menyuntik prompt), plus perintah `memory prune`.
3. **Observability** — simpan `tool_calls` terstruktur (nama, durasi, exit code) ke tabel terpisah, bukan sekadar string di `messages.content`.
4. **Sub-agent pool** dengan batas konkurensi + timeout, menggantikan delegasi serial rekursif.
5. **MCP client** agar tool discovery dinamis tanpa mengedit kode.

---

## 8. Ringkasan satu kalimat

> Arsitektur Laction Agent sudah benar sejak PR #1; review ini menutup celah-celah implementasi di keamanan, persistensi, dan batas konteks — sehingga harness-nya kini cukup aman untuk mulai dipasangi LLM sungguhan.

---

## 9. Catatan scope pasca-review (2026-11-16)

Angka di §5 (47 test, 10 doctor check, 3 guard) adalah **status saat PR review #2** dan tetap mencatat verifikasi historisnya. Setelah review, permintaan lanjutan menambah 5 tools (`run_python`, `web_search`, `rag_search`, `apk_analyze`, `apk_extract`), provider alias Gemini, 9 skill bawaan, serta panduan planning/verifikasi dan batas katalog skill 2.200 karakter.

Status kode terkini: **33 tools, 16 skill bawaan, 146 unittest lulus, doctor 25 check (termasuk FTS5, `memory prune`, `tool_events`, sandbox backend, MCP stdio roundtrip), wheel memuat 16 SKILL.md**. Detail keputusan fitur yang dipilih/ditunda, sumber riset, dan batasan keamanan tersedia di [`SKILLS.md`](SKILLS.md).
