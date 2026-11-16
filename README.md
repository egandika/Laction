# 🛰️ Laction Agent

> AI agent lokal untuk repo **Laction** — terinspirasi arsitektur **Hermes Agent (Nous Research)**, tapi dirancang ringan: **zero dependency eksternal**, **local-first**, dan **langsung jalan tanpa API key** lewat mode `mock`.

Catatan: ini bukan *Hermes 4* (model LLM) dan bukan klien Nous Portal. Hermes Agent adalah **harness/agent loop** di atas model apa pun. Laction Agent meniru pola harness itu, bukan menyalin kodenya.

---

## 1. Kenapa desain ini?

Repo ini awalnya hanya berisi `README.md`, jadi saya rancang agent yang:

| Kebutuhan | Keputusan desain |
|---|---|
| Bisa dicoba sekarang juga | `MockProvider` memahami perintah Bahasa Indonesia sederhana & menjalankan tools sungguhan |
| Tidak ribet install | Python 3.11+ **stdlib saja** (`urllib`, `sqlite3`, `http.server`, `argparse`) |
| Data tetap milik user | `MEMORY.md`, `USER.md`, `sessions.db`, `skills/`, `cron.json` di `LACTION_HOME` (default `./data`, di-gitignore) |
| Model-agnostic | Satu interface `BaseProvider`; OpenAI / OpenRouter / Gemini / Ollama / Nous / endpoint custom lewat format Chat Completions |
| Bisa tumbuh | Agent dapat mengusulkan `SKILL.md` baru; penulisan memerlukan approval |
| Guard dasar | Path traversal dibatasi dan shell/Python perlu approval; ini bukan sandbox dan bukan jaminan keamanan |
| Bukan cuma CLI | Ada Gateway HTTP + UI chat vanila JS, plus cron scheduler |

### Pemetaan 6 layer Hermes → Laction

| Hermes | Implementasi Laction |
|---|---|
| Surface / Gateway | `cli.py`, `gateway.py` (HTTP + UI) |
| Session / Profile | `Config.home` + `LACTION_HOME`, `SessionDB` (SQLite) |
| Reasoning | `providers/` (`mock`, OpenAI-compatible: OpenAI/OpenRouter/Gemini/Ollama/Nous) |
| Memory | `memory/` (Tier 1 Markdown + Tier 2 SQLite + workspace BM25 RAG) |
| Skill | `skills/` (`SKILL.md` bawaan + buatan agent) |
| Execution | `tools/` (file, shell/Python, web search/fetch, local RAG, APK statis, memory/skill, cron, delegasi) |

Dokumen lanjutan:
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — desain mendalam, diagram Mermaid, trace satu turn.
- [`docs/REVIEW.md`](docs/REVIEW.md) — **review kode**: penjelasan cara kerja tiap bagian, 9 temuan bug (termasuk 3 celah keamanan), perbaikan, dan risiko residual.
- [`docs/SKILLS.md`](docs/SKILLS.md) — analisis riset daftar skill, fitur yang dipilih/ditunda, batasan, dan sumber.
- [`docs/AGENTIC.md`](docs/AGENTIC.md) — batasan orkestrasi tim, cron read-only, approval, dan simulasi.
- [`docs/METHODS.md`](docs/METHODS.md) — analisis riset 47 metode/teknik agent (A–H), pemetaan ke Laction, dan template prompt efektif.

---

## 2. Quickstart (tanpa API key)

```bash
# Opsi A: langsung dari source, tanpa install
python3 -m laction_agent doctor
python3 -m laction_agent "list file"

# Opsi B: install editable (dapat perintah `laction`)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
laction status
```

Contoh pertama kali:

```text
$ laction "halo"
Halo! Saya Laction Agent (mode mock, tanpa API key). Perintah yang saya pahami: ...

$ laction "list file"
Selesai ✅ Saya sudah menjalankan tool untuk: "list file"
Hasil:
• 📄 .env.example
• 📄 README.md
• 📁 laction_agent
...
```

Mode `mock` benar-benar memanggil tool: baca/tulis file, jalankan shell, simpan memori, buat skill, sampai spawn sub-agent.

---

## 3. Perintah utama

```bash
laction "list file"                         # one-shot
laction "baca file README.md"
laction "tulis file catatan.txt isi halo"
laction chat  # di chat: jalankan git status --short (perlu approval)
laction "ingat: saya lebih suka Bahasa Indonesia"
laction "apa yang kamu ingat?"
laction "cari ingatan kopi"
laction "RAG search: konfigurasi provider"      # retrieval lokal, BM25
laction "cari web: dokumentasi Python 3.13"       # query keluar ke DuckDuckGo
laction "analisis APK aplikasi.apk"               # APK milik/yang boleh diaudit
laction chat                                     # di dalam chat: Python: print(1 + 1), perlu approval
laction "list skill"
laction "lihat skill repo-onboarding"
laction chat  # di chat: buat skill ringkas-repo: 1. list file 2. baca README (perlu approval)
laction "delegasikan: list tool"
laction "tim: list file"                     # dua spesialis + reviewer read-only
laction "debat: list file"                   # debat 1-putaran pro vs contra + reviewer
laction "cek kesehatan"                     # RAM + storage, read-only
laction 'evolusi: {"options":[{"name":"A","cost":1,"benefits":[2,3]}],"budget":1}'
laction "list cron"
laction "tambah cron harian | list file | 3600"

laction chat                                # REPL interaktif (/help, /tools, /memory, /new, /exit)
laction status --json                       # inspeksi config & state
laction tools --json                        # skema JSON semua tool
laction skills code-review                  # lihat isi SKILL.md
laction memory add "repo ini pakai stdlib"
laction init                                # buat profil data
laction cron list | add | remove | start
laction gateway --host 0.0.0.0 --port 8000 # UI + API
laction doctor                              # health check
```

### Gateway / UI

```bash
laction gateway --host 0.0.0.0 --port 8000
# buka http://localhost:8000  (atau URL preview 0.0.0.0 bila di sandbox)
```

Endpoint: `GET /health`, `/config`, `/tools`, `/skills`, `/memory`, `/history?session_id=...`, `/cron`; `POST /chat`, `/cron`, `/memory`, `/reset`.

Contoh API:

```bash
curl -s http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"list skill","session_id":"s-demo"}' | jq .reply
```

Kalau dipasang di jaringan, set token:

```bash
LACTION_GATEWAY_TOKEN=rahasia laction gateway --port 8000
# kirim header: Authorization: Bearer rahasia
```

---

## 4. Pakai LLM sungguhan

Salin contoh env, lalu edit:

```bash
cp .env.example .env
```

```dotenv
LACTION_PROVIDER=openai
LACTION_API_KEY=sk-...
LACTION_MODEL=gpt-4o-mini
# LACTION_API_BASE opsional untuk openai/openrouter/nous/ollama;
# wajib untuk provider=custom
```

Atau pakai `config.yaml`:

```bash
cp config.yaml.example config.yaml
```

Prioritas: **environment proses > `.env` > `config.yaml` > default**.

Provider yang didukung:

| Nilai | Base default | Catatan |
|---|---|---|
| `mock` | – | Tanpa jaringan, untuk demo/test |
| `openai` | `https://api.openai.com/v1` | Butuh API key |
| `openrouter` | `https://openrouter.ai/api/v1` | Butuh API key; pilih model di OpenRouter |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai` | Endpoint Gemini OpenAI-compatible; butuh API key + nama model |
| `nous` | `https://inference-api.nousresearch.com/v1` | Butuh API key |
| `ollama` | `http://localhost:11434/v1` | Lokal, tanpa key |
| `custom` / `openai_compat` | **wajib diisi** | Endpoint apa pun yang kompatibel dengan Chat Completions + `tools` |

Semua provider non-mock memakai `urllib` (tanpa `requests`). Format tool mengikuti OpenAI function calling, jadi ganti provider tidak mengubah tool registry. Gemini memakai compatibility endpoint resminya; kemampuan khusus tiap model/provider bisa berbeda.

---

## 5. Struktur repo

```text
Laction/
├── README.md                  # dokumen ini
├── docs/ARCHITECTURE.md       # desain mendalam + diagram alur
├── docs/REVIEW.md             # review kode, temuan bug & perbaikan
├── docs/SKILLS.md             # analisis daftar skill, riset & scope fitur
├── pyproject.toml             # packaging, entry point `laction`, pytest config
├── .env.example               # template environment
├── config.yaml.example        # template config YAML
├── LICENSE                    # MIT
├── laction_agent/
│   ├── __init__.py            # versi
│   ├── __main__.py            # python3 -m laction_agent
│   ├── cli.py                 # surface CLI: one-shot, REPL, status, cron, gateway
│   ├── config.py              # env + .env + YAML, validasi, redaksi
│   ├── prompt_builder.py      # system prompt dari MEMORY.md / USER.md / skills
│   ├── context_compressor.py  # ringkas riwayat, jaga tool-call pairing
│   ├── agent.py               # 🔁 loop utama + sub-agent delegation
│   ├── gateway.py             # HTTP API + UI chat (stdlib http.server)
│   ├── providers/             # BaseProvider + mock/OpenAI-compatible (termasuk Gemini)
│   ├── tools/                 # registry + 29 tool (self-register via decorator)
│   ├── memory/                # MemoryManager (Markdown) + SessionDB (SQLite)
│   ├── skills/                # SkillManager + 16 skill bawaan (SKILL.md)
│   └── cron/                  # CronScheduler (cron.json + thread)
└── tests/                     # unittest, juga bisa jalan via pytest
```

---

## 6. Daftar tool (29)

| Tool | Fungsi |
|---|---|
| `read_file`, `write_file`, `list_files`, `search_files` | Akses file workspace dengan guard path traversal |
| `run_terminal` | Shell lokal 30 detik, selalu perlu approval eksplisit; bukan sandbox |
| `run_python` | Runner kode Python, timeout 1–30 detik, **persetujuan eksplisit selalu**; bukan sandbox |
| `web_search`, `web_fetch` | Pencarian DDG best-effort + baca halaman publik; pencarian mengirim query ke DDG |
| `rag_search` | Retrieval lokal BM25 pada file teks, mengembalikan path/baris (bukan vector embeddings) |
| `apk_analyze`, `apk_extract` | Triage APK read-only + ekstraksi satu entry terbatas; APK tidak dijalankan |
| `memory_save`, `memory_read`, `user_save` | Tier-1 memory: `MEMORY.md` / `USER.md` |
| `memory_search` | Tier-2: cari riwayat sesi di SQLite |
| `list_skills`, `view_skill`, `create_skill` | Procedural memory / self-improvement |
| `delegate_task`, `consult_team` | Sub-agent read-only; tim spesialis (`apk`/`research`/`report`) atau debat 1-putaran (`pro`/`contra`) + reviewer, bukan sandbox |
| `device_health` | RAM dan storage read-only |
| `simulate_files`, `evolve_plan` | Dunia file virtual in-memory dan simulasi evolusi numerik terbatas; tidak menerapkan perubahan |
| `cron_add`, `cron_list`, `cron_remove` | Jadwal berulang |
| `get_time`, `list_tools`, `agent_info` | Utilitas sistem |

Tool mendaftar sendiri lewat `@reg.register(...)`. Menambah tool = tulis satu fungsi + skema JSON, tidak perlu menyentuh `agent.py`.

---

## 7. Memory & skill: closed learning loop

```text
tugas selesai
   ├─ fakta/preferensi  ──> memory_save / user_save ──> MEMORY.md / USER.md
   ├─ urutan kerja      ──> create_skill          ──> data/skills/<nama>/SKILL.md
   └─ jejak eksekusi    ──> SessionDB             ──> data/sessions.db
                                   │
                    system prompt sesi berikutnya memuat memory + daftar skill
```

Skill baru memerlukan approval eksplisit dan tidak boleh menimpa skill yang sudah ada. Ini prosedur tertulis, bukan pelatihan model atau kode yang otomatis teruji.

Skill bawaan (13): `repo-onboarding`, `code-review`, `release-notes`, `self-improvement`, `planning`, `reflection`, `python-debugging`, `git-workflow`, `android-apk-static-analysis`, `local-rag`, `public-web-research`, `provider-setup`, `productivity-workflows`.

`SKILL.md` memakai frontmatter `name` + `description` mengikuti [Agent Skills spec](https://agentskills.io/specification): katalog ringkas dimuat saat sesi, isi lengkap dibaca via `view_skill` bila diperlukan. Skill bawaan divalidasi namanya/frontmatter-nya oleh test.

---

## 8. Keamanan

- **Workspace guard**: `read_file`/`write_file`/`list_files` menolak path yang `.resolve()` keluar dari workspace.
- **Approval mode**:
  - `smart` (default) dan `always`: semua `run_terminal`, `run_python`, dan `create_skill` perlu persetujuan eksplisit.
  - `never`: shell, Python dan pembuatan skill tidak dijalankan.
- **Deteksi perintah berbahaya** mencakup rangkaian `;`, `&&`, `||`, `|`, substitusi `$(...)` dan backtick — bukan cuma kata pertama.
- **SSRF guard**: `web_fetch` menolak loopback/private/link-local/`localhost`/`.internal`, termasuk hasil DNS. Opt-out: `LACTION_ALLOW_PRIVATE_WEB=1`.
- **Web search**: `web_search` memakai HTML DuckDuckGo yang tidak resmi, bisa rate-limit/berubah; query dikirim ke pihak ketiga. Pola credential umum ditolak, tetapi jangan kirim secret/data privat.
- **Python runner**: `run_python` tidak memakai shell tetapi tetap arbitrary code dengan hak user, bukan sandbox; selalu fail-closed tanpa approval interaktif.
- **APK tools**: `apk_analyze` hanya membaca ZIP/AXML/strings dengan batas ukuran, `apk_extract` menulis satu entry ke workspace; tidak menjalankan APK dan bukan pengganti audit penuh.
- **RAG**: `rag_search` hanya file teks lokal yang diizinkan, mengecualikan `data/`, hidden dirs, `.git`, virtualenv, dan output build; retrieval BM25 leksikal, bukan vector.
- **Redaksi secret**: token `sk-*`, `ghp_*`, `github_pat_*`, `xox*-*`, `AKIA...`, `AIza*`, `Bearer ...`, dan `api_key=...` disamarkan sebelum masuk log, `sessions.db`, `MEMORY.md`, `USER.md`, maupun `SKILL.md`.
- **Batas konteks**: memory yang disuntik ke system prompt dibatasi 6.000 karakter terbaru; katalog skill maks 40 entri dan 2.200 karakter.
- **Penanganan error tool** (bukan sandbox): exception di tool diubah jadi string `{"error": ...}`, agent tetap hidup.
- **Provider error** ditangkap dan di-redaksi, tidak membocorkan API key ke log.
- **Gateway**: tanpa token jangan diekspos publik; aktifkan `LACTION_GATEWAY_TOKEN` + reverse proxy. Gateway masih CORS `*`, tanpa TLS/rate-limit.
- `data/`, `.env`, `config.yaml`, `*.db*`, `*.log` sudah di-`.gitignore`.

> `run_terminal` masih berupa `shell=True` + daftar blokir, dan `run_python` menjalankan kode dengan hak user — keduanya **bukan sandbox**. Gunakan hanya di workspace tepercaya; untuk produksi rencanakan backend Docker/SSH. Lihat [`docs/REVIEW.md`](docs/REVIEW.md) §6.

---

## 9. Test

```bash
python3 -m unittest discover -s tests -v
# atau, kalau pytest terpasang:
pip install -e ".[dev]"
python3 -m pytest -q
```

**79 test** mencakup config/provider (termasuk Gemini), tool registry, file guard, loop mock, memory, skills, delegasi, context compressor, CLI/gateway, Python approval, BM25 RAG, parser DuckDuckGo, APK text/binary AXML + zip-slip guard, routing mock, dan regresi keamanan (`tests/test_review_fixes.py`, `tests/test_added_capabilities.py`, `tests/test_agentic_workflows.py`).

`laction doctor` juga memverifikasi 5 guard keamanan (redaksi, terminal, SSRF, approval Python, path RAG).

CI GitHub Actions (`.github/workflows/ci.yml`) otomatis jalan di **Python 3.11 / 3.12 / 3.13** untuk setiap push & pull request: compile, unittest, `doctor`, editable install, smoke test entry point `laction`, dan smoke test HTTP gateway.

---

## 10. Batasan & roadmap

Belum ada (sengaja, supaya inti tetap ringan): MCP client/server, Honcho/remote memory, vector embeddings, optimisasi skill DSPy/GEPA, backend sandbox Docker/SSH/Modal, adapter WhatsApp/Telegram, multi-user auth, analisis APK dinamis (Frida/Logcat), YouTube transcript, image generation/analysis, dan speech-to-text/text-to-speech. Daftar keputusan + alasan ada di [`docs/SKILLS.md`](docs/SKILLS.md); risiko residual keamanan ada di [`docs/REVIEW.md`](docs/REVIEW.md) §6.

Rencana lanjutan paling masuk akal (berurutan sesuai prioritas review):

1. **Sandbox eksekusi** (`DockerExecutor`) — penting sebelum memasang LLM sungguhan.
2. FTS5 asli untuk `memory_search` + `memory prune` (saat ini `LIKE`, dan `MEMORY.md` append-only).
3. Observability tool: simpan nama/durasi/exit code terstruktur, bukan string di `messages.content`.
4. `SubagentPool` paralel dengan batas konkurensi + timeout.
5. `MCPClient` + tool discovery dinamis, lalu gateway adapter (webhook).

---

## 11. Lisensi

MIT — lihat [`LICENSE`](LICENSE).


## 12. Multi-agent & simulasi terbatas

`consult_team` membatasi 1–2 spesialis read-only paralel plus reviewer; cron juga hanya read-only. `simulate_files` memakai dunia file in-memory, bukan shell/emulator. `evolve_plan` mengoptimalkan model angka dengan seleksi, crossover, mutasi dan batas resource; hasil tidak otomatis diterapkan atau dijamin optimal. Shell, Python dan penulisan skill baru memerlukan persetujuan interaktif. **Tidak ada sandbox OS untuk kode tak tepercaya.** Lihat [docs/AGENTIC.md](docs/AGENTIC.md) untuk contoh, keamanan, keterbatasan, dan sumber riset.
