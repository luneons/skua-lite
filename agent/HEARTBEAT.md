# HEARTBEAT.md — Sinyal Hidup Bot `Mele`

Tujuan: pemeriksanaan ringan yang bisa dijalankan manusia (atau cronjob)
tanpa harus login ke AQW, untuk memastikan komponen AI + riset masih sehat.

## 1. Pemeriksaan Manual (60 detik)

Jalankan dari folder `C:\Users\reswa\projects\skua-lite`:

```powershell
# 1) Tes regresi cepat (subset ~30 detik).
python -m pytest tests/test_research.py tests/test_aqw_knowledge.py -q

# 2) Probe cache lokal.
python -c "from pathlib import Path; from skua_lite.research import ResearchCache; c = ResearchCache(Path(r'%LOCALAPPDATA%\skua-lite\research_cache')); n = sum(1 for _ in c._base.glob('*.json')); print('cache entries:', n)"

# 3) Probe riset live/Wayback (read-only, cache temporer).
python -m skua_lite.research "https://aqwwiki.wikidot.com/archpaladin | ArchPaladin class"

# 4) Probe endpoint AI (tanpa menyimpan secret ke log).
python -c "from skua_lite.ai_router import AIConfig; cfg=AIConfig.from_env(); print('configured=',cfg.configured,'timeout=',cfg.timeout,'max_tokens=',cfg.max_tokens)"

# 5) Tes Admin Mode + wiring owner-only.
python -m pytest tests/test_agent_tools.py tests/test_admin_commands.py tests/test_admin_mode.py tests/test_admin_wiring.py -q

# 6) Probe child-env aman + eksekusi kode nyata.
python -c "from skua_lite.agent_tools import AgentTools; import os; t=AgentTools(os.getcwd()); print('secret_leak=', 'SKUA_AI_API_KEY' in t._child_env()); print(t.run_code('print(6*7)').summary)"
```

Kalau salah satu gagal, jangan langsung restart — cek log dulu.

## 2. Pemeriksaan Otomatis (cronjob, opsional)

Skrip `scripts/heartbeat.py` (lihat di bawah) mengembalikan kode keluar 0 jika
semua OK, non-zero jika ada masalah. Cocok dipasang di Task Scheduler
Windows tiap 30 menit.

## 3. Sinyal Hidup ke Room AQW

Bot **tidak** mengirim pesan periodik otomatis ke room (anti-spam). Sinyal
hidup hanya melalui:

- Log `[AI]` ke `runner.out` (default stdout saat `JALANKAN_SKUA_LITE.bat`).
- File `presence_capture.log` yang ditulis setiap event `uER`/`userGone`.
- Memori AI di `%LOCALAPPDATA%\skua-lite\ai_memory.json` (cek `len(_memory)`
  sebelum dan sesudah restart untuk konfirmasi persistensi).

## 4. Tanda-Tanda Tidak Sehat

| Tanda | Cek |
| --- | --- |
| Bot diam, tidak ada log | Proses mati — lihat PID di Task Manager; restart via batch. |
| `[AI] riset '...' gagal: network blocked` muncul terus | Koneksi ke Bing/Wayback down; bot tetap jawab dari lokal, tidak fatal. |
| `_memory` selalu 0 setelah restart | `memory_path` salah tulis; `runner.py` akan log path yang dipakai. |
| Chat panjang (>150 char) lolos ke channel | `_safe_reply`/sanitizer rusak; jalankan `pytest tests/test_ai_router.py -q`. |

## 5. Tindakan Darurat

1. Matikan proses: `powershell stop pid <PID>`.
2. Hapus cache riset jika korup: `rmdir /s %LOCALAPPDATA%\skua-lite\research_cache`.
3. Restart via `JALANKAN_SKUA_LITE.bat`.
4. Tunggu ~1 menit lalu masuk memakai akun pemilik dan coba `!status` untuk
   konfirmasi Admin Mode + memori.