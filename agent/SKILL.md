# SKILL.md — SOP Riset Bot `Mele`

Tujuan: satu helah "terselesaikan" saat seorang instruktur bertanya di AQW
dan jawaban offline belum ada. Bukan instruksi untuk model; SOP untuk
komponen riset di dalam bot (`research.Researcher` + `ai_router`).

## 1. Pre-conditions

- `ResearchCache` sudah ada di `%LOCALAPPDATA%/skua-lite/research_cache/`.
- Folder `panduan/` berisi panduan lokal; bila kosong, sistem tetap jalan
  dengan jawaban seadanya.
- `.env` minimal berisi `SKUA_AI_BASE_URL`, `SKUA_AI_API_KEY`,
  `SKUA_AI_MODEL`. Bila kosong, bot OFFLINE tanpa AI.

## 2. Loop Riset (pseudo input minta detection)

1. Gatekeeper melihat pesan masuk. Bila ada konteks lokal yang relevan
   (panduan + glosarium), itu yang dipakai duluan — tidak ada riset.
2. Bila gatekeeper gagal memenuhi, `Reasoner` memanggil model. Model
   boleh menjawab langsung, **atau** membalas tepat `RESEARCH: <topik>`.
3. `Reasoner` mem-parse marker. Bila iya:
   a. Catat `(original_text, topic)` di `_research_seen_keys`.
   b. Panggil `Researcher.answer(topic)`.
      - Cache hit → pakai teks, label `cache`.
      - Bing/DuckDuckGo live → ambil URL pertama, fetch, label `live`.
      - Gagal → fallback Wayback untuk URL yang sama, label `wayback`.
      - Kalau semua gagal → label `none`, alasan dicatat.
   c. Sambungkan hasil ke prompt sebagai blok `HASIL RISET (...)` atau
      `RISET TIDAK TERSEDIA (...)` lalu minta Reasoner menjawab ulang.
4. Hasil Reasoner kedua dikirim ke channel dengan sanitizer
   `_strip_source_mentions`. Marker `RESEARCH:` dan URL internal
   dihapus.

## 3. Fallback yang Sah

| Situasi | Tindakan |
| --- | --- |
| Bing/Google live dapat 0 hasil. | Coba slug AQW Wiki langsung (`/stonecrusher`, `/stonecrusher-class`, dst). |
| AQW Wiki timeout. | Coba Wayback `archive.org/wayback/available`. |
| Wayback tidak punya snapshot. | Balas `Belum ada data terverifikasi`. |
| Riset kedua tetap `RESEARCH:` lagi. | Stop — pakai jawaban model apa adanya, sanitizer buang marker. |

## 4. Anti-Pattern

- **Jangan** riset saat panduan lokal punya jawaban (boros kuota, alasan
  risiko halusinasi).
- **Jangan** riset untuk pertanyaan non-AQW.
- **Jangan** menulis/menghapus file di luar `research_cache/`.
- **Jangan** cache teks kosong (`source == "none"`).
- **Jangan** paparkan URL AQW Wiki atau label `Wayback` di chat AQW.

## 5. Pengujian

- Unit test: `tests/test_research.py` (helper murni, tidak ada HTTP).
- Integrasi: `tests/test_ai_router.py::test_agent_*` (mock Researcher).
- Live probe: `python -m skua_lite.research "https://aqwwiki.wikidot.com/archpaladin | ArchPaladin class"`.

## 6. Pemeliharaan

| Gejala | Penyebab umum | Tindakan |
| --- | --- | --- |
| Riset selalu `none` | Bing/Google menampilkan shell kosong. | Cek `extract_wiki_urls` masih mengenali domain `aqwwiki.wikidot.com`; fallback slug wajib ada. |
| Snapshot basi | Wayback simpan > 6 bulan. | Biarkan — timestamp ditampilkan via log, bukan ke chat. |
| Cache membengkak | URL duplikat disimpan. | Tambah LRU di `ResearchCache` (TODO). |