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
| Execution | `tools/` (file, shell/Python, web search/fetch, local RAG, APK statis, memory/skill, cron, delegasi, MCP) |

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

laction chat                                # REPL interaktif (/help, /tools, /memory, /traces, /new, /exit)
laction status --json                       # inspeksi config & state
laction tools --json                        # skema JSON semua tool
laction skills code-review                  # lihat isi SKILL.md
laction memory add "repo ini pakai stdlib"
laction memory prune --max-entries 50 --max-chars 6000
laction traces --limit 20                   # durasi & status tiap panggilan tool
laction traces --prune --keep 10000          # retensi: simpan 10k event terbaru
laction mcp add --name demo --command python3 --args -m laction_agent.mcp.demo_server \
  --allow-tools ping workspace_summary            # allowlist per-tool (opsional tapi disarankan)
laction mcp list | tools --name demo | allow --name demo --tools ping | remove --name demo
laction --workspace /path/ke/proyek --sandbox-mode docker chat
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

Endpoint: `GET /health`, `/config`, `/tools`, `/skills`, `/memory`, `/history?session_id=...`, `/cron`, `/traces?session_id=...`, `/mcp`; `POST /chat`, `/cron`, `/memory` (termasuk `{"action":"prune"}`), `/reset`. UI punya tombol **Traces**, **MCP**, **Prune memory**, **Prune traces**, dan **Uji koneksi** MCP.

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
│   ├── team.py                # fan-out spesialis/debat + deadline wall-clock
│   ├── sandbox.py             # DockerExecutor opsional (fail-closed)
│   ├── mcp/                   # registry allowlist + klien JSON-RPC stdio + demo server
│   ├── tools/                 # registry + 33 tool (self-register via decorator)
│   ├── memory/                # MemoryManager (Markdown) + SessionDB (SQLite FTS5)
│   ├── skills/                # SkillManager + 16 skill bawaan (SKILL.md)
│   └── cron/                  # CronScheduler (cron.json + thread)
└── tests/                     # unittest, juga bisa jalan via pytest
```

---

## 6. Daftar tool (33)

| Tool | Fungsi |
|---|---|
| `read_file`, `write_file`, `list_files`, `search_files` | Akses file workspace dengan guard path traversal |
| `run_terminal` | Shell 30 detik, selalu perlu approval eksplisit; lokal atau container Docker bila `sandbox_mode` aktif |
| `run_python` | Runner kode Python, timeout 1–30 detik, **persetujuan eksplisit selalu**; lokal atau container Docker |
| `web_search`, `web_fetch` | Pencarian DDG best-effort + baca halaman publik; pencarian mengirim query ke DDG |
| `rag_search` | Retrieval lokal BM25 pada file teks, mengembalikan path/baris (bukan vector embeddings) |
| `apk_analyze`, `apk_extract` | Triage APK read-only + ekstraksi satu entry terbatas; APK tidak dijalankan |
| `memory_save`, `memory_read`, `user_save` | Tier-1 memory: `MEMORY.md` / `USER.md` |
| `memory_search` | Tier-2: cari riwayat sesi di SQLite (FTS5 + ranking BM25, fallback `LIKE`) |
| `memory_prune` | Pangkas + deduplikasi `MEMORY.md`/`USER.md`, simpan entri terbaru |
| `list_skills`, `view_skill`, `create_skill` | Procedural memory / self-improvement |
| `delegate_task`, `consult_team` | Sub-agent read-only; tim spesialis (`apk`/`research`/`report`) atau debat 1-putaran (`pro`/`contra`) + reviewer, bukan sandbox |
| `device_health` | RAM dan storage read-only |
| `simulate_files`, `evolve_plan` | Dunia file virtual in-memory dan simulasi evolusi numerik terbatas; tidak menerapkan perubahan |
| `cron_add`, `cron_list`, `cron_remove` | Jadwal berulang |
| `mcp_list_servers`, `mcp_list_tools`, `mcp_call` | Klien MCP `stdio` dengan allowlist server + per-tool, validasi argumen, dan approval wajib |
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

Skill bawaan (16): `repo-onboarding`, `code-review`, `release-notes`, `self-improvement`, `planning`, `reflection`, `python-debugging`, `git-workflow`, `android-apk-static-analysis`, `local-rag`, `public-web-research`, `provider-setup`, `productivity-workflows`, `adversarial-thinking`, `structured-reflexion`, `verification-cove`.

`SKILL.md` memakai frontmatter `name` + `description` mengikuti [Agent Skills spec](https://agentskills.io/specification): katalog ringkas dimuat saat sesi, isi lengkap dibaca via `view_skill` bila diperlukan. Skill bawaan divalidasi namanya/frontmatter-nya oleh test.

---

## 8. Keamanan

- **Workspace eksplisit**: root file tools ditentukan `--workspace` > `LACTION_WORKSPACE` > `cfg.workspace` > `cwd` saat proses mulai. `read_file`/`write_file`/`list_files`/`rag_search` menolak path yang `.resolve()` keluar dari root tersebut.
- **File kontrol dilindungi**: `write_file` menolak menimpa `mcp_servers.json`, `cron.json`, dan `SKILL.md`; perubahan hanya lewat tool/perintah yang punya validasi + approval.
- **Approval mode**:
  - `smart` (default) dan `always`: semua `run_terminal`, `run_python`, dan `create_skill` perlu persetujuan eksplisit.
  - `never`: shell, Python dan pembuatan skill tidak dijalankan.
- **Deteksi perintah berbahaya** mencakup rangkaian `;`, `&&`, `||`, `|`, substitusi `$(...)` dan backtick — bukan cuma kata pertama.
- **SSRF guard**: `web_fetch` menolak loopback/private/link-local/`localhost`/`.internal`, termasuk hasil DNS. Opt-out: `LACTION_ALLOW_PRIVATE_WEB=1`.
- **Web search**: `web_search` memakai HTML DuckDuckGo yang tidak resmi, bisa rate-limit/berubah; query dikirim ke pihak ketiga. Pola credential umum ditolak, tetapi jangan kirim secret/data privat.
- **Python runner**: `run_python` tidak memakai shell, tetapi pada `sandbox_mode=none` tetap arbitrary code dengan hak user; selalu fail-closed tanpa approval interaktif.
- **Sandbox Docker opsional** (`LACTION_SANDBOX_MODE=none|auto|docker`): `DockerExecutor` menjalankan shell/Python di container `--network none`, root `--read-only`, `/tmp` `noexec,nosuid,size=64m`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 64`, `--memory 256m`, `--cpus 1.0`, user `65534:65534`, hanya workspace yang di-mount (`ro`). Mode `docker` **fail-closed** bila binary/ daemon Docker tidak siap; mode `auto` turun ke eksekusi lokal. Container tetap berbagi kernel host dan workspace `ro` masih bisa dibaca, jadi approval tetap wajib.
- **MCP allowlist berlapis**: hanya server di `<LACTION_HOME>/mcp_servers.json` yang bisa dijalankan (tidak ada auto-discovery); tiap server boleh punya allowlist `tools` sendiri, dan tool di luar daftar ditolak **sebelum** approval/ proses server dijalankan. Argumen divalidasi terhadap `inputSchema` (wajib-isi, tipe primitif, ukuran), approval diminta sebelum proses pihak ketiga di-spawn, dan klien punya watchdog wall-clock yang membunuh proses yang menggantung. Klien `stdio` memakai JSON-RPC 2.0, frame maks 1 MiB, timeout wall-clock, dan environment yang diwarisi hanya `PATH`/`HOME`/`LANG` + env server eksplisit (`LACTION_API_KEY` tidak bocor ke proses anak). `mcp_call` di luar `READ_ONLY_TOOLS` dan butuh approval.
- **Team deadline**: `consult_team` punya batas wall-clock total (`LACTION_TEAM_TIMEOUT`, default 45 detik, bisa ditimpa `timeout_seconds`); worker yang lewat batas dibatalkan dan hasilnya ditandai `TIMEOUT`.
- **APK tools**: `apk_analyze` hanya membaca ZIP/AXML/strings dengan batas ukuran, `apk_extract` menulis satu entry ke workspace; tidak menjalankan APK dan bukan pengganti audit penuh.
- **RAG**: `rag_search` hanya file teks lokal yang diizinkan, mengecualikan `data/`, hidden dirs, `.git`, virtualenv, dan output build; retrieval BM25 leksikal, bukan vector.
- **Redaksi secret terpusat**: token `sk-*`, `ghp_*`, `github_pat_*`, `xox*-*`, `AKIA...`, `AIza*`, `Bearer ...`, dan `api_key=...` disamarkan di dalam `MemoryManager`/`SessionDB`, jadi semua pintu masuk (tool, `laction memory add`, `POST /memory` gateway) ikut tersanitasi.
- **Batas ukuran memory**: `MEMORY.md`/`USER.md` dipangkas otomatis saat append melewati 32.000 karakter, dan `laction memory prune` / `POST /memory {"action":"prune"}` bisa memangkas eksplisit ke N entri & M karakter (entri terbaru dan duplikat ditangani).
- **Batas konteks**: memory yang disuntik ke system prompt dibatasi 6.000 karakter terbaru; katalog skill maks 40 entri dan 2.200 karakter.
- **Penanganan error tool** (bukan sandbox): exception di tool diubah jadi string `{"error": ...}`, agent tetap hidup.
- **Provider error** ditangkap dan di-redaksi, tidak membocorkan API key ke log.
- **Gateway**: tanpa token jangan diekspos publik; aktifkan `LACTION_GATEWAY_TOKEN` + reverse proxy. Gateway masih CORS `*`, tanpa TLS/rate-limit. Cache agent dibatasi 32 sesi (LRU) dan `/chat` memakai `run_lock` dengan batas tunggu 120 detik → `429` alih-alih menggantung tanpa batas.
- **Retensi observability**: `tool_events` bisa dipangkas dengan `laction traces --prune --keep N` atau `POST /traces {"keep": N}`; riwayat chat di tabel `messages` tidak disentuh. `laction status` menampilkan jumlah pesan/sesi/event + ukuran DB.
- **SQLite tahan gagal**: `sessions.db` memakai `journal_mode=WAL` + `busy_timeout` 10 detik, dan DB korup dikarantina (`sessions.db.corrupt-<timestamp>`) lalu dibuat ulang agar agent tidak mati total.
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

**146 test** mencakup config/provider (termasuk Gemini), tool registry, file guard, loop mock, memory, skills, delegasi, context compressor, CLI/gateway, Python approval, BM25 RAG, parser DuckDuckGo, APK text/binary AXML + zip-slip guard, routing mock, serta paket terbaru: FTS5 + `prune` + redaksi terpusat, `tool_events`/metrics, workspace eksplisit, flag `DockerExecutor`, deadline tim, dan roundtrip MCP stdio (`tests/test_next_packages.py`).

`laction doctor` (25 check) juga memverifikasi guard keamanan & kemampuan baru: redaksi, terminal chain/substitusi, SSRF, approval Python, path RAG, FTS5, `memory prune`, redaksi memory, `tool_events`, workspace eksplisit, backend sandbox, registry MCP, roundtrip server MCP demo, `journal_mode=WAL`, retensi `tool_events`, pemulihan DB korup, dan allowlist tool MCP.

CI GitHub Actions (`.github/workflows/ci.yml`) otomatis jalan di **Python 3.11 / 3.12 / 3.13** untuk setiap push & pull request: compile, unittest, `doctor`, editable install, smoke test entry point `laction`, dan smoke test HTTP gateway.

---

## 10. Batasan & roadmap

Belum ada (sengaja, supaya inti tetap ringan): MCP di atas transport HTTP/SSE, Honcho/remote memory, vector embeddings, optimisasi skill DSPy/GEPA, backend sandbox SSH/Modal, adapter WhatsApp/Telegram, multi-user auth, analisis APK dinamis (Frida/Logcat), YouTube transcript, image generation/analysis, dan speech-to-text/text-to-speech. Daftar keputusan + alasan ada di [`docs/SKILLS.md`](docs/SKILLS.md); risiko residual keamanan ada di [`docs/REVIEW.md`](docs/REVIEW.md) §6.

Rencana lanjutan paling masuk akal (berurutan sesuai prioritas review):

1. **Sandbox produksi**: `gVisor`/`Firecracker` atau seccomp profile kustom di atas `DockerExecutor`; saat ini container berbagi kernel host.
2. **Observability lanjutan**: agregasi `tool_events` lintas sesi, alerting, dan ekspor OpenTelemetry (sekarang tabel lokal + `laction traces` + `GET /traces`).
3. **MCP lebih luas**: transport HTTP/SSE dan OAuth (kini `stdio` saja). Allowlist per-tool & validasi `inputSchema` sudah ada.
4. **Subagent pool** dengan batas konkurensi adaptif; deadline wall-clock sudah ada di `team.py`.
5. `MCPClient` + tool discovery dinamis, lalu gateway adapter (webhook).

---

## 11. Lisensi

MIT — lihat [`LICENSE`](LICENSE).


## 12. Multi-agent & simulasi terbatas

`consult_team` membatasi 1–2 spesialis read-only paralel plus reviewer; cron juga hanya read-only. `simulate_files` memakai dunia file in-memory, bukan shell/emulator. `evolve_plan` mengoptimalkan model angka dengan seleksi, crossover, mutasi dan batas resource; hasil tidak otomatis diterapkan atau dijamin optimal. Shell, Python dan penulisan skill baru memerlukan persetujuan interaktif. **Tidak ada sandbox OS untuk kode tak tepercaya.** Lihat [docs/AGENTIC.md](docs/AGENTIC.md) untuk contoh, keamanan, keterbatasan, dan sumber riset.
