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
| Model-agnostic | Satu interface `BaseProvider`; OpenAI / OpenRouter / Ollama / Nous / endpoint custom lewat format Chat Completions |
| Bisa tumbuh | Agent bisa menulis `SKILL.md` baru dari pengalaman (*closed learning loop*) |
| Aman dipakai di repo | Path traversal dicegah, terminal punya `approval_mode`, tool error tidak bikin agent crash |
| Bukan cuma CLI | Ada Gateway HTTP + UI chat vanila JS, plus cron scheduler |

### Pemetaan 6 layer Hermes → Laction

| Hermes | Implementasi Laction |
|---|---|
| Surface / Gateway | `cli.py`, `gateway.py` (HTTP + UI) |
| Session / Profile | `Config.home` + `LACTION_HOME`, `SessionDB` (SQLite) |
| Reasoning | `providers/` (`mock`, `openai_compat`) |
| Memory | `memory/` (Tier 1 Markdown + Tier 2 SQLite) |
| Skill | `skills/` (`SKILL.md` bawaan + buatan agent) |
| Execution | `tools/` (file, terminal, web, memory, skill, cron, delegasi) |

Detail lengkap ada di [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

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
laction "jalankan git status --short"
laction "ingat: saya lebih suka Bahasa Indonesia"
laction "apa yang kamu ingat?"
laction "cari ingatan kopi"
laction "list skill"
laction "lihat skill repo-onboarding"
laction "buat skill ringkas-repo: 1. list file 2. baca README 3. simpan ringkasan"
laction "delegasikan: list tool"
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
| `openrouter` | `https://openrouter.ai/api/v1` | Butuh API key |
| `nous` | `https://inference-api.nousresearch.com/v1` | Butuh API key |
| `ollama` | `http://localhost:11434/v1` | Lokal, tanpa key |
| `custom` / `openai_compat` | **wajib diisi** | Endpoint apa pun yang kompatibel dengan Chat Completions + `tools` |

Semua provider non-mock memakai `urllib` (tanpa `requests`). Format tool mengikuti OpenAI function calling, jadi ganti provider tidak mengubah tool registry.

---

## 5. Struktur repo

```text
Laction/
├── README.md                  # dokumen ini
├── docs/ARCHITECTURE.md       # desain mendalam + diagram alur
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
│   ├── providers/             # BaseProvider, MockProvider, OpenAICompatProvider
│   ├── tools/                 # registry + 20 tool (self-register via decorator)
│   ├── memory/                # MemoryManager (Markdown) + SessionDB (SQLite)
│   ├── skills/                # SkillManager + 4 skill bawaan (SKILL.md)
│   └── cron/                  # CronScheduler (cron.json + thread)
└── tests/                     # unittest, juga bisa jalan via pytest
```

---

## 6. Daftar tool

| Tool | Fungsi |
|---|---|
| `read_file`, `write_file`, `list_files`, `search_files` | Akses file workspace (dengan guard path traversal) |
| `run_terminal` | Shell 30 detik + approval + blokir perintah berbahaya |
| `web_fetch` | Ambil halaman web jadi teks polos |
| `memory_save`, `memory_read`, `user_save` | Tier-1 memory: `MEMORY.md` / `USER.md` |
| `memory_search` | Tier-2: cari riwayat sesi di SQLite |
| `list_skills`, `view_skill`, `create_skill` | Procedural memory / self-improvement |
| `delegate_task` | Sub-agent dengan sesi terisolasi (maks depth 2) |
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

Skill bawaan: `repo-onboarding`, `code-review`, `release-notes`, `self-improvement`.

`SKILL.md` memakai frontmatter `name` + `description` (konvensi agentskills.io), jadi mudah dipindah ke agent lain.

---

## 8. Keamanan

- **Workspace guard**: `read_file`/`write_file`/`list_files` menolak path yang.resolve() keluar dari repo.
- **Approval mode**:
  - `smart` (default): hanya perintah berbahaya yang minta persetujuan di REPL.
  - `always`: semua `run_terminal` minta persetujuan.
  - `never`: perintah berbahaya diblokir total.
- **Tool isolation**: exception di tool diubah jadi string `{"error": ...}`, agent tetap hidup.
- **Provider error** ditangkap dan di-redaksi, tidak membocorkan API key ke log.
- **Gateway**: tanpa token jangan diekspos publik; aktifkan `LACTION_GATEWAY_TOKEN` + reverse proxy.
- `data/`, `.env`, `config.yaml`, `*.db*`, `*.log` sudah di-`.gitignore`.

---

## 9. Test

```bash
python3 -m unittest discover -s tests -v
# atau, kalau pytest terpasang:
pip install -e ".[dev]"
python3 -m pytest -q
```

Test mencakup config precedence, tool registry, file guard, loop mock (tidak infinite loop), memory lintas sesi, skill creation, delegasi, context compressor, routing CLI, dan helper gateway.

CI GitHub Actions (`.github/workflows/ci.yml`) otomatis jalan di **Python 3.11 / 3.12 / 3.13** untuk setiap push & pull request: compile, unittest, `doctor`, editable install, smoke test entry point `laction`, dan smoke test HTTP gateway.

---

## 10. Batasan & roadmap

Belum ada (sengaja, supaya inti tetap ringan): MCP client, Honcho/remote memory, DSPy/GEPA optimisasi skill, backend Docker/SSH/Modal, adapter WhatsApp/Telegram/Slack, dan multi-user auth.

Rencana lanjutan yang paling masuk akal:

1. `MCPClient` + tool discovery dinamis.
2. FTS5 asli untuk `memory_search` (saat ini `LIKE`).
3. `SubagentPool` paralel dengan batas konkurensi.
4. Backend eksekusi `DockerExecutor` untuk isolasi `run_terminal`.
5. Gateway adapter (CLI sudah ada, tinggal tambah webhook).

---

## 11. Lisensi

MIT — lihat [`LICENSE`](LICENSE).
