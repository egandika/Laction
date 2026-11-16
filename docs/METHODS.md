# Analisis 47 Metode Agent & Pemetaannya ke Laction

Riset dan audit implementasi tanggal **16 November 2026**. Dokumen ini memetakan seluruh 47 teknik pada daftar metode agent (kelompok A–H), **Rekap Pemula**, serta **Prompt Dewa** terhadap riset empiris dan arsitektur nyata `laction_agent`.

Prinsip utama: **pisahkan teknik yang memang butuh kode/orkestrasi dari teknik yang cukup lewat instruksi singkat, dan bedakan model reasoning modern dari model non-reasoning.**

---

## Ringkasan Cepat

- **Sudah menjadi bagian inti Laction (kode/loop):** ReAct (`AIAgent.run()`), Reflexion anti-loop guard (`agent.py`), Memory jangka pendek & panjang (`MEMORY.md`, `USER.md`, `SessionDB`, `rag_search`), Multi-agent bounded (`consult_team` mode `specialists` & `debate` + `Evaluator independen`, `delegate_task`), Simulasi & Evolusi numerik (`simulate_files`, `evolve_plan`), Human-in-the-loop approval (`run_terminal`, `run_python`, `create_skill`), dan Procedural Skills (`16` skill bawaan termasuk `planning`, `reflection`, `verification-cove`, `adversarial-thinking`, `structured-reflexion`).
- **Perbedaan penting model reasoning vs non-reasoning:** Panduan resmi OpenAI, Anthropic, dan Google (2025–2026) menegaskan bahwa model reasoning (seri o/GPT-5 reasoning, Claude extended thinking, Gemini thinking, DeepSeek R1) **tidak perlu** dipaksa *"think step by step"* atau CoT manual—instruksi seperti itu justru dapat menambah latency atau menurunkan kualitas [1](https://promptessor.com/blog/reasoning-model-prompting-guide) [2](https://techsy.io/en/blog/chain-of-thought-prompting). Gunakan CoT/Few-Shot manual hanya pada model non-reasoning/kecil, dan minta **bukti serta ringkasan yang dapat diaudit**, bukan chain-of-thought privat.
- **Kenapa "Prompt Dewa" 7-in-1 sering kontraproduktif:** Memaksa `Least-to-Most + ToT + CoT + ReAct + Reflexion + Evolutionary + Self-Verification` di setiap prompt membuat tugas sederhana lambat dan boros token, memicu *overthinking* pada model reasoning, serta memberi ilusi verifikasi jika tidak terhubung ke tool/test nyata.

---

## Pemetaan Lengkap 47 Metode (A–H)

### A. Metode Mikir Dasar (Reasoning)

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 1 | **Zero-Shot** | Default di semua mode | Pilihan terbaik pertama untuk model reasoning modern dan tugas jelas; hemat token dan tidak bias oleh contoh yang salah [1](https://promptessor.com/blog/reasoning-model-prompting-guide). |
| 2 | **Few-Shot** | Lewat prompt user atau `SKILL.md` | Berguna (1–2 contoh ketat) jika format output sangat spesifik atau pada model kecil; terlalu banyak contoh pada reasoning model bisa memperburuk hasil [2](https://techsy.io/en/blog/chain-of-thought-prompting). |
| 3 | **Chain-of-Thought (CoT)** | Tidak dipaksakan ke output | Efektif di model non-reasoning; **hindari** memaksa CoT terbuka pada reasoning model dan jangan menuntut chain-of-thought internal demi privasi/kebersihan konteks [1](https://promptessor.com/blog/reasoning-model-prompting-guide). |
| 4 | **Zero-Shot CoT** | Opsional di prompt untuk model kecil | Satu kalimat *"pecah langkahnya"* membantu model lokal/non-reasoning kecil, tapi berlebihan untuk model yang sudah berpikir internal [2](https://techsy.io/en/blog/chain-of-thought-prompting). |
| 5 | **Self-Consistency** | Belum otomatis di loop; bisa via prompt/skrip | Voting mayoritas meningkatkan akurasi pada jawaban diskrit (matematika/klasifikasi), tetapi gagal jika model punya *blind spot* sistematis yang sama atau pada tugas terbuka [3](https://arxiv.org/abs/2210.03629) [4](https://www.zhongzhuzhou.org/blog/2026-02-16-2026-02-16-TreeOfThoughts-technical-review-en/). |
| 6 | **Least-to-Most** | Didukung skill `planning` + prompt | Cocok saat masalah bisa dipecah bertahap dari submasalah sederhana ke kompleks; `planning/SKILL.md` memandu dekomposisi 3–7 langkah. |
| 7 | **Step-Back Prompting** | Lewat prompt / skill `adversarial-thinking` | Berguna saat terjebak detail gejala (mis. bug config/arsitektur) agar meninjau prinsip umum terlebih dahulu sebelum menyimpulkan. |
| 8 | **Analogical Reasoning** | Lewat prompt saja | Membantu menjelaskan konsep atau memicu ide awal, tetapi analogi (mis. pintu rusak vs HP) **tidak membuktikan** keamanan/isolasi teknis. |

### B. Metode Mikir Bercabang (Tree / Graph)

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 9 | **Tree of Thought (ToT)** | Terbatas di prompt / skill | Meningkatkan pemecahan masalah pencarian (seperti teka-teki/perencanaan berbatas), namun biaya token tumbuh eksponensial (`b^d`) dan sangat bergantung pada kualitas *evaluator*—penilaian LLM atas dirinya sendiri sering bias jika tanpa tool/verifier eksternal [4](https://www.zhongzhuzhou.org/blog/2026-02-16-2026-02-16-TreeOfThoughts-technical-review-en/). |
| 10 | **Graph of Thought (GoT)** | Tidak diotomasi | Butuh manajemen graf status & penggabungan cabang; tanpa evaluator objektif, penggabungan cabang di satu prompt sering sekadar merata-ratakan teks. |
| 11 | **Forest of Thought (FoT)** | Tidak diimplementasikan | Biaya beberapa pohon paralel sangat tinggi untuk chat lokal/Termux; tidak sepadan untuk tugas harian tanpa verifier otomatis. |
| 12 | **Branch-Solve-Merge** | **Diimplementasikan sebagian:** `consult_team(mode="specialists")` | Cabang spesialis read-only (`apk`, `research`, `report`) berjalan paralel lalu disintesis dan ditinjau reviewer terpisah [5](AGENTIC.md). |

### C. Metode Aksi + Mikir (Agentic)

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 13 | **ReAct (Reason + Act)** | **Inti `AIAgent.run()`** | Loop `provider.chat → tool → observation` mengikat penalaran ke bukti tool nyata, menekan halusinasi dibanding CoT murni [3](https://arxiv.org/abs/2210.03629). |
| 14 | **ReWOO** | Dapat dipakai lewat prompt untuk tugas baca-saja | Hemat round-trip jika langkah tidak saling bergantung, tetapi rapuh jika langkah ke-2 butuh hasil langkah ke-1 (file tidak ditemukan, error tak terduga). |
| 15 | **Reflexion** | **Inti `agent.py` (guard) + skill `structured-reflexion`** | Efektif ketika umpan balik berasal dari kegagalan terverifikasi (error tool/test), bukan tebakan [3](https://arxiv.org/abs/2210.03629). `AIAgent.run()` memblokir panggilan gagal/ditolak yang identik dalam satu giliran agar agent tidak berputar di tempat. |
| 16 | **Self-Refine** | Didukung skill `reflection` & `verification-cove` | Kritik diri tanpa bukti eksternal berisiko mengubah jawaban benar menjadi salah atau hanya memperhalus gaya bahasa; kaitkan selalu dengan cek file/test. |
| 17 | **Self-Debug** | **Lebih baik pakai tool:** `run_python` / `unittest` (dengan approval) | "Menjalankan kode di otak" jauh lebih lemah daripada mengeksekusi unit test atau `run_python` dengan persetujuan user. Gunakan skill `python-debugging`. |
| 18 | **Plan-and-Solve** | Didukung skill `planning` + approval gate | `run_terminal`, `run_python`, dan `create_skill` meminta persetujuan interaktif sebelum dijalankan; untuk edit file berisiko, minta rencana terlebih dahulu lewat prompt. |
| 19 | **Plan-and-Execute (Interleaved)** | **Didukung default** di `planning/SKILL.md` + loop ReAct | Merencanakan langkah, menjalankan, mengamati hasil, lalu menyesuaikan rencana berikutnya jauh lebih aman saat kondisi workspace berubah. |

### D. Metode Multi-Agent

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 20 | **Debate** | **Diimplementasikan terbatas:** `consult_team(mode="debate")` | Riset 2025–2026 (*The Cost of Consensus*; *A Layered Analysis of Disagreement*) menunjukkan debat homogen multi-putaran menghabiskan **2,1–3,4× lebih banyak token** dan sering menurunkan akurasi akibat *sycophancy* (ikut mayoritas) [6](https://www.alphaxiv.org/abs/2605.00914) [7](https://pith.science/paper/2609.08016). Karena itu Laction membatasinya **1 putaran paralel (`pro` vs `contra`, read-only)** lalu dinilai `Evaluator independen` berbasis bukti. |
| 21 | **Role-Play / Persona** | Lebih aman via `consult_team` | Pura-pura menjadi 3 orang dalam 1 prompt tidak menambah alat ukur atau sumber baru; pemisahan konteks read-only per spesialis lebih bersih, meski tetap bergantung pada kualitas model. |
| 22 | **Mixture of Experts (MoE)** | **Klarifikasi istilah** + `consult_team` | Secara teknis, MoE adalah arsitektur routing bobot internal di jaringan saraf, bukan pembagian peran prompt. Pola pembagian tugas di level agent lebih tepat disebut **Specialist Routing / Orchestrator** (`consult_team`). |
| 23 | **Supervisor / Orchestrator** | **Inti `AIAgent` + `consult_team` + `delegate_task`** | Agent utama membagi sub-tugas read-only ke 1–2 spesialis paralel (maks 4 iterasi), lalu menyintesis hasil akhir [5](AGENTIC.md). |
| 24 | **Critic / Evaluator** | **Inti `team.py`** (pass `Evaluator independen`) | Reviewer membandingkan temuan terhadap tugas dengan menandai temuan spesialis sebagai **data tak tepercaya**. |
| 25 | **Generator - Discriminator** | Didukung lewat `consult_team` atau `evolve_plan` | Pemisahan penghasil kandidat dan penyaring efektif jika penyaring memiliki kriteria/skor eksplisit atau bukti tool, bukan sekadar preferensi acak. |

### E. Metode Evolusi / Simulasi

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 26 | **Evolutionary Prompt** | Prinsip lewat prompt / skill | Menggabungkan kelebihan beberapa draf dapat membantu penulisan atau desain, tetapi tanpa metrik objektif hasilnya tidak dijamin "super". |
| 27 | **Genetic Algorithm** | **Tool `evolve_plan`** | Menjalankan populasi, evaluasi maximin atas skenario, seleksi, crossover, mutasi, dan elitisme dengan `seed` tetap. Terbatas pada model angka input (maks 20 opsi, 10 skenario, 64 populasi, 10 generasi); bukan optimasi kode/HP otomatis. |
| 28 | **Best-of-N** | Sebagian di `evolve_plan` / prompt | Efektif hanya bila tersedia fungsi skor atau verifikator yang tepat; menghasilkan 10 jawaban panjang di satu prompt tanpa evaluator justru memboroskan konteks. |
| 29 | **Monte Carlo / What-If** | **Tool `evolve_plan` (skenario) + `adversarial-thinking`** | `evolve_plan` menguji kombinasi opsi terhadap banyak skenario sekaligus (mis. beban/biaya/gangguan), sedangkan analisis skenario kualitatif memakai teknik Inversion. |
| 30 | **Parallel Simulation (Sandbox Mini)** | **Tool `simulate_files`** | Menyediakan dunia file virtual **in-memory** (`read/write/delete/list`, maks 40 file / 64 KiB / 50 aksi). **Bukan** sandbox OS, bukan emulator Android, dan tidak menjalankan shell/APK sungguhan. |

### F. Metode Memori / Belajar

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 31 | **Memory / Reflection Memory** | **Inti `MEMORY.md` + `structured-reflexion`** | Pelajaran yang sudah terverifikasi disimpan dengan `memory_save` (maks 6.000 karakter terbaru dimuat ke system prompt, kredensial disamarkan heuristik). |
| 32 | **Long-Term Memory** | **Inti `MemoryManager` + `SessionDB` + `rag_search`** | `MEMORY.md` & `USER.md` (Tier 1), riwayat SQLite + `memory_search` (Tier 2), dan BM25 leksikal atas workspace (`rag_search`). |
| 33 | **Experience Replay** | Didukung lewat `memory_search` + `SKILL.md` | Mengambil riwayat sesi atau prosedur `SKILL.md` lama untuk masalah serupa. Bukan pembaruan bobot *reinforcement learning*. |
| 34 | **Curriculum Learning** | Lewat prompt / penjelasan bertahap | Berguna sebagai gaya mengajar dari konsep dasar ke lanjut; tidak melatih ulang model. |

### G. Metode Verifikasi / Anti-Ngarang

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 35 | **Self-Verification** | **Inti `prompt_builder.py` + `reflection` skill** | Memeriksa kecocokan hasil terhadap permintaan, diff, dan output tool sebelum menjawab. |
| 36 | **Fact-Check / Hallucination Check** | **Skill `verification-cove`** | Memisahkan klaim `[TERVERIFIKASI: sumber]` vs `[BELUM DIVERIFIKASI]` / `[ASUMSI]`, alih-alih label `[NEBAK]` yang informal. |
| 37 | **Confidence Score** | **Diganti bukti & ketidakpastian eksplisit** | Riset kalibrasi LLM menunjukkan skor percaya diri verbal 1–100 sering meleset jauh (*overconfident* pada halusinasi). Lebih andal mencantumkan bukti verifikasi dan apa yang masih belum diuji. |
| 38 | **Chain-of-Verification (CoVe)** | **Skill `verification-cove`** | Studi Dhuliawala et al. (2023) menunjukkan pemisahan *draft → verification questions → independent tool/fact execution → final revision* menurunkan halusinasi secara signifikan karena pertanyaan dijawab terpisah dari bias draf awal [8](https://arxiv.org/abs/2309.11495). |

### H. Metode Khusus & Eksperimental

| # | Metode | Status di Laction | Analisis Riset & Batasan |
|---|---|---|---|
| 39 | **Prompt Chaining** | **Inti `delegate_task`, `consult_team`, & skill** | Memecah tugas besar menjadi subtugas fokus menjaga konteks tetap bersih. |
| 40 | **Meta-Prompting** | Lewat prompt (maks 1 kali revisi) | Bermanfaat jika prompt awal terlalu kabur untuk dirapikan terlebih dahulu menjadi spesifikasi jelas sebelum eksekusi. |
| 41 | **Recursive Prompting** | Tidak disarankan tanpa batas | Mengulang revisi sampai *"perfect"* mudah memicu loop mahal tanpa kriteria berhenti objektif. Selalu tetapkan batas iterasi dan kriteria berhenti terukur. |
| 42 | **Socratic Method** | **Skill `adversarial-thinking`** | Efektif untuk spesifikasi ambigu sebelum aksi berisiko; hindari menanyakan ulang hal yang sudah jelas atau bisa dicek langsung lewat `read_file`. |
| 43 | **Devil's Advocate** | **`consult_team(mode="debate")` + `adversarial-thinking`** | Mencari titik lemah rencana secara sengaja mengurangi *confirmation bias*. |
| 44 | **First Principles** | **Skill `adversarial-thinking`** | Membongkar masalah ke fakta dasar terukur (file, batas RAM/storage, izin) sebelum memilih solusi. |
| 45 | **Reverse Thinking / Inversion** | **`consult_team(mode="debate")` + `adversarial-thinking`** | Menganalisis cara rencana gagal total lalu memasang guard untuk tiap kegagalan. |
| 46 | **Swarm / Ant Colony** | **Tidak diimplementasikan** | Menyuruh 1 LLM *"bayangkan 20 semut"* hanya simulasi imajinatif; ACO sungguhan butuh graf numerik, feromon, dan fungsi biaya. Menjalankan 20 agent LLM paralel tidak efisien untuk penggunaan lokal. |
| 47 | **Darwin-Gödel Machine (DGM)** | **Tidak diimplementasikan (berisiko tanpa sandbox & benchmark)** | Riset DGM (ICLR 2026 / arXiv:2505.22954) membuktikan peningkatan kemampuan coding lewat **arsip kode agent + evaluasi empiris pada SWE-bench/Polyglot**, dan secara eksplisit **menghapus eskalasi hak akses serta mewajibkan sandbox terisolasi** [9](https://arxiv.org/abs/2505.22954v3) [10](https://en.papernotes.org/ICLR2026/llm_agent/darwin_g%C3%B6del_machine_open-ended_evolution_of_self_improving_agents/). Mengizinkan agent menulis ulang kodenya sendiri secara bebas di lingkungan user tanpa sandbox dan suite benchmark terisolasi adalah risiko keamanan serius. |

---

## Rekomendasi Praktis: Pengganti "Prompt Dewa" di Laction

Alih-alih menempel 7 metode sekaligus ke setiap chat, pilih pola sesuai tugas:

1. **Tugas harian / cepat** *(baca file, cek status, tugas jelas)*:
   > Langsung tulis perintah spesifik (Zero-Shot + ReAct otomatis). Contoh: `"cek kesehatan"` atau `"RAG search: konfigurasi provider"`.

2. **Audit / analisis mendalam & anti-halusinasi** *(pakai CoVe + First Principles)*:
   > `"Audit [target] memakai skill verification-cove. Periksa bukti langsung dengan tool (read_file/search_files/apk_analyze), pisahkan fakta [TERVERIFIKASI] dari [BELUM DIVERIFIKASI], dan jangan tampilkan chain-of-thought internal."`

3. **Keputusan desain / pilihan berisiko** *(pakai Inversion + Debate 1-putaran + Plan-and-Solve)*:
   > `"Gunakan skill adversarial-thinking dan consult_team mode debate untuk menguji opsi [A vs B]. Jabarkan cara gagal terburuk (inversion), bandingkan bukti, dan ajukan rencana langkah 1–5 untuk saya setujui sebelum mengubah file atau menjalankan perintah."`

---

## Referensi Riset

- [1] Reasoning model prompting practices (OpenAI/Anthropic/Gemini summary): <https://promptessor.com/blog/reasoning-model-prompting-guide>
- [2] Chain-of-Thought prompting vs reasoning models: <https://techsy.io/en/blog/chain-of-thought-prompting>
- [3] Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models* (arXiv:2210.03629): <https://arxiv.org/abs/2210.03629>
- [4] Yao et al., *Tree of Thoughts: Deliberate Problem Solving with Large Language Models* (review & limits): <https://www.zhongzhuzhou.org/blog/2026-02-16-2026-02-16-TreeOfThoughts-technical-review-en/>
- [5] Batasan orkestrasi & keamanan Laction: [`docs/AGENTIC.md`](AGENTIC.md)
- [6] *The Cost of Consensus: Isolated Self-Correction Prevails Over Unguided Homogeneous Multi-Agent Debate* (2026): <https://www.alphaxiv.org/abs/2605.00914>
- [7] *A Layered Analysis of Disagreement And Answer Quality in Multi-Agent LLM Debate* (2026): <https://pith.science/paper/2609.08016>
- [8] Dhuliawala et al., *Chain-of-Verification Reduces Hallucination in Large Language Models* (arXiv:2309.11495): <https://arxiv.org/abs/2309.11495>
- [9] Zhang et al., *Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents* (arXiv:2505.22954): <https://arxiv.org/abs/2505.22954v3>
- [10] Ringkasan ICLR 2026 DGM (sandbox & benchmark evaluation): <https://en.papernotes.org/ICLR2026/llm_agent/darwin_g%C3%B6del_machine_open-ended_evolution_of_self_improving_agents/>
