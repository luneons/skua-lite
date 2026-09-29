# `agent/` — Operating Charter for skua-lite

> Dokumen ini menjelaskan bagaimana komponen AI + riset otomatis di
> `skua-lite` saling beroperasi. Tujuan: satu helah “terselesaikan” saat
> seorang instruktur bertanya di AQW dan jawaban offline belum ada.

## Struktur

- `SKILL.md` — SOP loop riset (cache, fallback Wayback, anti-loop).
- `HEARTBEAT.md` — sinyal hidup, langkah darurat, dan perintah
  diagnostik yang aman dijalankan manual.

## Identitas Bot

- Startup punya dua flow tetap: `AI ASISTEN` dan `FARMING`.
- AI Asisten: nama `Mele`, akun pemilik `MELE` / `ME LE`; bahasa Indonesia
  singkat, sopan, ≤150 karakter; router `OFF`/`ON`/`ADMIN MODE`.
- Farming: AI/Admin/Riset/Hermes tools tidak dibangun. Runtime hanya memakai
  paket SFS terverifikasi dan karakter tidak AFK otomatis.

## Loop Riset (satu putaran)

```
chat → Gatekeeper
      └── ada konteks lokal?  ── ya ──► Reasoner (jawab final)
                          tidak
                              │
                              ▼
                          Reasoner (1)
                              │
                              ├── output final        ──► chat
                              └── "RESEARCH: <topic>" ──► Researcher
                                                          │
                                                          ├── cache hit
                                                          ├── Bing/DDG live
                                                          ├── Wayback fallback
                                                          └── gagal ⇒ "RISET TIDAK TERSEDIA"
                              │
                              ▼
                          Reasoner (2) ──► chat (sanitizer ≤150 karakter)
```

## Kontrak Wajib

1. `RESEARCH:` adalah protokol internal — tidak pernah bocor ke chat.
2. Riset **maks satu putaran** per pesan; pasangan `(pesan_asli, topik)`
   dicatat di `_research_seen_keys` agar tidak looping.
3. Cache disimpan di `%LOCALAPPDATA%\skua-lite\research_cache\` (JSON per
   URL). Tidak ada file yang ditulis/dihapus di tempat lain.
4. Sumber internal (nama file, URL AQW Wiki, frasa `(sumber: …)`) tidak
   pernah muncul di channel AQW — `_strip_source_mentions` adalah janji
   keras, bukan panduan.
5. Endpoint AI + secret tetap di `.env`; tidak ada fallback hard-coded.
6. Bot offline (tanpa AI) bila env kosong — tidak ada jawaban palsu dari
   teks statis.
7. Perintah admin hanya jalan untuk UID/nama pemilik aktif; non-owner
   `!...` dikembalikan sebagai tidak dikonsumsi.

## Lokasi Kode

| Komponen | File |
| --- | --- |
| Gatekeeper + Reasoner | `src/skua_lite/ai_router.py` |
| Startup mode gate | `src/skua_lite/mode.py` |
| Farming runtime tanpa AI | `src/skua_lite/farming.py` |
| Researcher + cache | `src/skua_lite/research.py` |
| Glosarium class/enhancement | `src/skua_lite/aqw_knowledge.py` |
| Panduan ultra | `src/skua_lite/ultra_guide.py` |
| Orchestrator + wiring + Admin actions | `src/skua_lite/runner.py` |
| Parser/dispatcher perintah admin | `src/skua_lite/admin_commands.py` |
| Tools nyata + bukti verifikasi | `src/skua_lite/agent_tools.py` |

## Lokasi Tes

| Tes | Berkas |
| --- | --- |
| Helper murni (URL, HTML→text, marker) | `tests/test_research.py` |
| Agent loop + satu putaran | `tests/test_ai_router.py::test_agent_*` |
| Glosarium class/enhancement | `tests/test_aqw_knowledge.py` |
| Panduan ultra | `tests/test_ai_router.py::test_ultra_guide_*` |
| Perintah admin (parse, konfirmasi, gerak) | `tests/test_admin_commands.py` |
| Admin Mode di router (owner-only, klamp 150) | `tests/test_admin_mode.py` |
| Tools nyata (env bersih, allowlist, upgrade) | `tests/test_agent_tools.py` |
| Wiring runner + jalur chat → admin → zone | `tests/test_admin_wiring.py` |
| Pilihan mode + pemisah flow asisten/farming | `tests/test_mode_selection.py` |
| Builder/paket + runtime farming tanpa AI | `tests/test_farming.py` |