---
name: provider-setup
description: Konfigurasikan provider LLM OpenAI-compatible seperti OpenRouter, Gemini, Ollama, atau endpoint custom tanpa menaruh API key di source code. Gunakan saat menghubungkan model.
---

# Provider Setup

## Gemini
Provider `gemini` memakai endpoint compatibility resmi dan format tool-calling OpenAI-compatible:

```dotenv
LACTION_PROVIDER=gemini
LACTION_API_KEY=... # simpan di .env lokal atau environment, jangan commit
LACTION_MODEL=<model yang tersedia di Google AI Studio>
```

## Provider lain
- OpenRouter: `LACTION_PROVIDER=openrouter`, API key + model slug OpenRouter.
- Ollama: `LACTION_PROVIDER=ollama`, model lokal dan URL OpenAI-compatible yang dapat dijangkau.
- Endpoint kompatibel lain: `LACTION_PROVIDER=openai_compat`, isi `LACTION_API_BASE`, `LACTION_API_KEY`, dan `LACTION_MODEL`.

## Cek aman
1. Hindari menampilkan nilai API key di terminal/chat; gunakan `laction status` untuk memastikan key terdeteksi (nilai disamarkan).
2. Jalankan `laction doctor`, lalu uji permintaan sederhana.
3. Ingat bahwa request dan prompt dikirim ke provider yang dipilih; jangan mengirim data privat tanpa persetujuan.

Fitur khusus provider yang tidak ada di Chat Completions standar (mis. media, grounding, atau parameter thinking tertentu) tidak otomatis tersedia.