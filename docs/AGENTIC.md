# Orkestrasi, evaluasi, dan simulasi yang dibatasi

Riset 16 November 2026. Contoh seperti 100 agent, APK palsu, dan digital twin adalah motivasi, **bukan klaim bahwa semuanya sudah didukung**. Tujuan implementasi ini adalah memberi fondasi yang bisa dicoba pada Python 3.11+/Termux tanpa dependensi tambahan, bukan menjalankan kode tak tepercaya di HP.

Lihat juga [`docs/METHODS.md`](METHODS.md) untuk pemetaan lengkap 47 metode reasoning/agentic/verifikasi beserta hasil riset dan batasannya.

## Apa yang benar-benar tersedia

| Kebutuhan | Implementasi | Batas penting |
|---|---|---|
| Multi-agent | `consult_team`: mode `specialists` (1–2 role `apk`, `research`, `report`) atau mode `debate` (1 putaran paralel `pro` vs `contra`) + reviewer terpisah sesudahnya. Agent induk menyatukan jawaban. `delegate_task` tetap ada. | Tiap anak punya sesi terpisah, tool read-only yang diizinkan dan maksimal 4 iterasi, 8 tool call per respons. Tidak ada subdelegasi dari anak. Hanya satu tim berjalan sekaligus. Ini **bukan** isolasi OS; provider dapat memakan waktu hingga timeout jaringan per panggilan, tanpa deadline total. Reviewer bisa salah dan bukan bukti independen otomatis. Mock hanya parser/template, bukan evaluator cerdas. |
| Self-improvement & Reflexion | `create_skill` menyimpan prosedur `SKILL.md` setelah approval eksplisit, menolak nama skill yang sudah ada; skill tidak boleh menimpa skill bawaan. Loop `AIAgent.run()` memiliki *Reflexion guard* yang memblokir panggilan tool gagal/ditolak yang persis sama dalam satu giliran. | Ini tidak menulis/menguji tool baru, tidak melatih bobot model, dan bukan jaminan prosedur benar. Isi ditampilkan sebelum approval; tolak bila meragukan. Jalankan pengujian terpisah untuk perubahan kode, jangan jalankan kode yang tidak dipercaya. |
| Autonomous | Cron yang ada menjalankan tugas berulang, sekarang dengan tool read-only dan maksimum 3 job aktif per scheduler; hasil disimpan dalam sesi. `device_health` membaca RAM `/proc/meminfo` bila tersedia dan ruang disk workspace. | Scheduler harus hidup, bukan layanan otomatis saat boot. Tidak membersihkan RAM, tidak mematikan aplikasi, tidak mengirim notifikasi, tidak berjanji mencapai tujuan; job yang melebihi batas aktif dilewati sampai interval berikutnya. |
| Safety | Registry menegakkan allowlist saat dispatch, bahkan jika model memanggil tool yang tidak diberikan; anak dan cron tak dapat memanggil shell, penulisan file, jaringan atau delegasi. `run_python`, `run_terminal`, dan pembuatan skill selalu memerlukan approval interaktif; `never` memblokir shell/Python. | Approval **bukan sandbox**. Agent utama masih memiliki `write_file`, `apk_extract`, web, memory dan cron; tidak semua side effect meminta approval. Shell/Python yang disetujui berhak atas OS user; denylist bukan perlindungan file sistem. Jangan gunakan untuk kode tak tepercaya atau produksi tanpa isolasi dan kontrol yang lebih kuat. |
| Dunia simulasi | `simulate_files` menjalankan operasi `read/write/delete/list` atas peta file **di memori saja**, maksimum 40 file/64 KiB/50 operasi. | Ini simulasi state virtual terbatas, **bukan** shell, OS, APK, emulator, container, atau VM. Tidak menguji efek perintah sungguhan dan tidak menyalin HP. Tidak ada otomatis apply ke dunia nyata. |
| Evolusi | `evolve_plan` menggunakan input opsi numerik dengan cost, manfaat per skenario, budget; mengevaluasi skor skenario terburuk, seleksi, crossover, mutasi dan elitisme. Seed tetap menghasilkan run yang dapat diulang. Maks 20 opsi, 10 skenario, 64 populasi dan 10 generasi. | Hanya optimasi model angka yang diberikan, bukan 100 agent/HP atau APK nyata. Angka/fitness harus berasal dari asumsi atau pengukuran yang dibenarkan; crossover tidak selalu memperbaiki dan optimum/perfect tidak dijamin. Tidak melakukan self-training atau menerapkan solusi. |
| MCP, 1000 agent, model belajar dari mimpi/emosi | Belum ada. | Ini butuh riset, protocol/izin, pembatasan biaya dan isolasi teruji; istilah emosi/simulasi bukan bukti pengalaman subjektif. |

### Privasi dan trust

Sub-agent dan cron memakai sesi serta memory/skill yang sama secara lokal; riwayat disimpan di SQLite dan redaksi secret hanya heuristik. Dengan provider cloud, input, memory, konten file/tool yang dibaca dan hasil tim dapat dikirim ke provider. Tool baca file dapat membaca data sensitif dalam workspace. Jangan berikan data privat tanpa memahami tujuan dan kebijakan provider. Izinkan riset web eksternal secara terpisah; role `research` dalam tim ini **hanya data lokal**, tidak melakukan OSINT internet. Output file, APK, dan model adalah data tak tepercaya dan rentan prompt injection. `approval_mode=never` bukan mode aman universal.

## Contoh nyata

```bash
laction 'cek kesehatan'
laction 'tim: list file'  # mock menunjukkan alur, tidak melakukan penalaran evaluasi
laction 'evolusi: {"options":[{"name":"A","cost":2,"benefits":[4,3]},{"name":"B","cost":3,"benefits":[3,5]}],"budget":5,"seed":42}'
laction cron add --name pantau --task 'cek kesehatan' --interval 3600
laction cron start       # biarkan proses hidup; hasil tiap run ada di session DB
laction chat             # di sini tinjau approval sebelum membuat skill/menjalankan shell/Python
```

Untuk mencoba dunia file virtual langsung tanpa LLM:

```python
from laction_agent.tools.registry import get_registry
print(get_registry().call("simulate_files", {
    "files": {"draft.txt": "asli virtual"},
    "actions": [{"op": "delete", "path": "draft.txt"}, {"op": "list"}]
}))
```

Tidak ada file sungguhan dihapus atau dibuat. Mencoba `rm -rf` atau mengeksekusi APK tidak didukung. Untuk eksekusi tak tepercaya perlu backend isolasi OS/VM independen yang diverifikasi: identitas tak berprivilege, filesystem dan network terisolasi, batas CPU/memori/proses/waktu, serta tanpa secret; backend seperti itu belum disediakan oleh proyek ini.

## Sumber dan keputusan

- [OpenAI Agents SDK — guardrails dan human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals): terapkan batas di tool, approval sebelum side effect, fail closed. Dipakai sebagai prinsip, bukan dependency.
- [OWASP — Agentic AI context bypass](https://cornucopia.owasp.org/edition/companion/AAI2/1.0): least privilege dan memisahkan instruksi dari data; tidak ada klaim prompt injection terpecahkan.
- [Cornell — genetic algorithm](https://optimization.cbe.cornell.edu/index.php?title=Genetic_algorithm): population, fitness, selection, crossover, mutation. Fitness pada implementasi ini eksplisit, bukan evaluator umum.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): container memiliki risiko dan perlu pengaturan keamanan; folder sementara saja tidak menyediakan batas keamanan.
