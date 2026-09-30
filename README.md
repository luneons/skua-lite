# skua-lite

Rencana arsitektur dan roadmap jangka panjang untuk scanner area berbasis SWF +
state server ada di [`docs/RENCANA_INDUK.md`](docs/RENCANA_INDUK.md).

Versi ringan bot AQW berbasis **Python murni**. Tanpa Flash, tanpa browser —
hanya TCP socket + HTTP langsung ke server AQW. Saat start tersedia dua flow
terpisah: **MODE AI ASISTEN** dan **MODE FARMING**.

## Dua mode startup

Launcher tersedia untuk tiap OS:

- Windows: klik `JALANKAN_SKUA_LITE.bat`.
- Linux: jalankan `./JALANKAN_SKUA_LITE.sh`.
- macOS: klik `JALANKAN_SKUA_LITE.command` dari Finder atau jalankan
  `./JALANKAN_SKUA_LITE.sh` dari Terminal.

Launcher Linux/macOS otomatis mencari Python 3.11+, membuat `.venv`, memasang
package/dependency bila belum ada, lalu meneruskan semua argumen CLI. Jika file
hasil unduhan belum executable, jalankan sekali:

    chmod +x JALANKAN_SKUA_LITE.sh JALANKAN_SKUA_LITE.command

Jalankan launcher sesuai OS atau `python -m skua_lite`; sebelum login bot
selalu meminta pilihan:

    [1] MODE AI ASISTEN
        -> flow lama tetap utuh
        -> login, join yulgar-14045, gerak, lalu AFK
        -> AI chat, memori, riset, dan Admin Mode owner tersedia

    [2] MODE FARMING
        -> flow berbeda; tidak membuat AI router/Admin/Hermes tool
        -> login, join private lair-100000, karakter tetap ACTIVE
        -> menu farming: join, move, drop, rest, booster, aggro,
           quest turn-in, sell, bank, auto-attack Mage, combat capture
        -> tujuan agentic: `auto farming <monster>` atau `.auto farming <monster>`
           menjalankan loop observe -> decide -> act sampai `Berhenti`

Mode dapat dipilih noninteraktif memakai `--mode assistant` atau
`--mode farming`. Opsi `--map` mengoverride map default mode tersebut.

Auto-goal saat ini hanya mengeksekusi tujuan `farming <monster>` yang bisa
dibuktikan dari snapshot monster/cell server. Bentuk `cari <item> xN dari
<monster>` dan `selesaikan quest <id>` sudah diparse, tetapi runtime menolaknya
sampai pelacak inventory/progres quest tersedia; bot tidak berpura-pura sukses
atau farming tanpa batas dari state yang tidak dapat diamati.

Auto-attack awal tersedia untuk profil **Mage / farming cepat / Water
Draconian**. Engine membaca `moveToArea`, `updateClass`/inventory, `sAct`,
`mtls`, `uotls`, dan `respawnMon`; hanya monster hidup bernama sama di cell
aktif yang ditarget. Bentuk JSON live `uotls`/`mtls` yang menaruh state di
objek `o` juga didukung. Saat karakter mati, engine meniru alur client asli:
tunggu 10 detik, kirim `resPlayerTimed` sekali, lalu menanggapi `resTimed`
dengan `moveToCell` ke titik spawn. Urutan Mage berasal dari profil Skua 1.4.4
(`4,2,1,3`) dengan `aa` sebagai fallback. Target count/type dan cooldown tetap
dari metadata `sAct` live, bukan ditebak. `.capture on` sebelum uji live
pertama agar paket combat tersimpan lokal tanpa chat. `.attack auto`
menyerang semua monster hidup di cell aktif (nama dari scan `moveToArea`).

## Status verifikasi protokol

Semua format paket diambil dari **client AQW asli yang didecompile**
(Game.swf via FFDec) dan dikonfirmasi lawan server produksi:

| Item | Nilai | Sumber |
|---|---|---|
| Versi SFS (verChk) | 157 | SmartFoxClient.as (maj 1, min 5, sub 7) |
| Login zone | zone_master | Game.as cLoginZone |
| clientToken | SPIDER#0001 | Game.as clientToken |
| clientVersion | 4.372 | Game.as vParam |
| Login nick | SPIDER#0001~<user>~4.372 | Game.as line 555 |
| Login pword | objLogin.sToken | Game.as line 9946 |
| Join map | %xt%zm%cmd%<room>%tfer%<user>%<map>%<cell>%<pad>% | Chat.as, ScriptMap.cs |
| Chat zone | %xt%zm%message%<room>%<msg>%zone% | Chat.as |
| AFK | %xt%zm%cmd%<room>%afk% | PacketInterceptor.cs |
| Ambil drop | %xt%zm%getDrop%<room>%<drop_id>% | Skua ScriptDrop.cs |
| Rest | %xt%zm%restRequest%1%% | AQW World.as / Skua PacketLogger.cs |
| Booster/item | %xt%zm%serverUseItem%<room>%+%<item_id>% | Skua ScriptBoost.cs |
| Quest turn-in | %xt%zm%tryQuestComplete%...%wvz% | Skua ScriptQuest.cs |
| Bank/sell | loadBank, bankToInv, bankFromInv, bankSwapInv, sellItem | Skua ScriptBank/ScriptShop |
| Aggro monster | %xt%zm%aggroMon%<room>%<MonMapID>...% | AQW World.as / Skua ScriptInterface.cs |
| Akhir paket | null byte 0x00 | SmartFoxClient.writeToSocket |

Diuji live: TCP ke sock8.aq.com:5588 + verChk -> server balas apiOK.
Diuji live: POST api/login/now -> server mem-parse user/pass/option.

## Alur startup

    python -m skua_lite
      -> pilih MODE AI ASISTEN atau MODE FARMING
      -> prompt username & password (tidak ditampilkan; disimpan terenkripsi)
      -> HTTP login ke game.aq.com/game/api/login/now (ambil sToken)
      -> ambil server dari content.aq.com/game/api/data/servers
      -> TCP connect + verChk + login zone_master + getRmList + firstJoin
      -> jalankan flow dan menu khusus mode yang dipilih

## Menu AI Asisten

    [1] CHAT     -> kirim chat ke zone (ketik: chat <pesan>)
    [2] ACTION   -> reload | logout | minimize | hide
    [3] STATUS   -> state, map, room id, afk
    [0] QUIT

Shortcut langsung: chat <pesan>, reload, logout, minimize/bg, hide, status, quit.

minimize mengecilkan window konsol ke taskbar; hide menyembunyikannya total —
bot tetap berjalan di latar belakang.

## Menu Farming

Semua command farming memakai prefix titik:

    skua-farm> .status
    skua-farm> .join lair-100000
    skua-farm> .move 850 302
    skua-farm> .combat
    skua-farm> .area
    skua-farm> .area json
    skua-farm> .capture on
    skua-farm> .chat halo semua
    skua-farm> .chat /join yulgar-14045
    skua-farm> .chat /goto mele
    skua-farm> .cells
    skua-farm> .cell Stairs
    skua-farm> .cell Cave BottomLeft
    skua-farm> .attack Water Draconian
    skua-farm> .attack auto
    skua-farm> .attack off
    skua-farm> lawan semua musuh yang ada di map ini
    skua-farm> berhenti lawan musuh
    skua-farm> .goal map
    skua-farm> .goal stop
    skua-farm> .drop <drop_id>
    skua-farm> .rest
    skua-farm> .booster <item_id>
    skua-farm> .aggro <MonMapID> [MonMapID ...]
    skua-farm> .quest <quest_id> [reward_id] [turn_ins]
    skua-farm> .sell <item_id> <qty> <char_item_id>
    skua-farm> .bank load
    skua-farm> .bank in <item_id> <char_item_id>
    skua-farm> .bank out <item_id> <char_item_id>

`.attack <nama>` memfilter monster hasil scan berdasarkan nama. `.attack auto`
tidak memakai filter nama: engine memilih semua monster hidup dalam cell/frame
karakter dari snapshot `moveToArea`, lalu mengikuti update `mtls`/`respawnMon`.
Monster di cell lain tidak diserang.

`.area` menampilkan snapshot dinamis atomik dari wire: generasi area, room,
diri, pemain, monster, cell/pad, HP/state, `event`, dan `cellMap`. Setiap nilai
saat ini berprovenance `[wire]`; `.area json` menghasilkan JSON deterministik
schema v1. Setiap `moveToArea` menaikkan generation dan mengganti semua entity
area lama, sehingga paket yang ditandai generation lama tidak bisa menghidupkan
monster/pemain dari map sebelumnya. Replay offline memakai fixture sintetis
tersanitasi di `tests/fixtures/area/`.

`.cells` menampilkan destinasi yang benar-benar ditemukan. Bot menggabungkan
cell yang tampak pada `moveToArea` (diri sendiri, monster, pemain lain) dengan
semua label frame yang dapat dibaca dari SWF map bernama `strMapFileName`.
Untuk bertarung, jangan mikir per command: cukup ucapkan tujuannya
(`lawan semua musuh di map ini`) atau jalankan `.goal map`. Engine memakai
area scan yang sama untuk melawan semua monster hidup di cell aktif, pindah
satu hop ke cell yang masih punya musuh (paket `moveToCell` yang sama),
menunggu konfirmasi `uotls`/`moveToArea` dari server, lalu lanjut melawan.
`berhenti lawan musuh` / `.goal stop` menghentikan tujuan. Timeout perpindahan
2 detik dengan satu retry terbatas; cell yang gagal dijangkau diblokir dan
dilaporkan, bukan dispam.
SWF berlangsung di thread terpisah sehingga receiver combat tidak tertahan, dan
hasil `.cells` tidak dipotong.
Kalau SWF tidak dapat diambil/diparse, output ditandai **scan server parsial**;
nama cell tidak pernah ditebak. `.cell <nama> [pad]` mengirim paket asli
`%xt%zm%moveToCell%<curRoom>%<cell>%<pad>%`. Jika pad tidak ditulis, bot
memakai pasangan cell/pad yang benar-benar sudah teramati; jika belum ada,
barulah fallback mengikuti client: `Enter -> Spawn`, cell lain -> `Left`. Pad
eksplisit seperti `Center`, `Bottom`, `BottomLeft`, `TopRight`, dan nama pad lain
dikirim apa adanya untuk divalidasi server. Contoh: `.cell Stairs Left`,
`.cell Cave BottomLeft`.

`.chat <pesan>` mengirim chat biasa. Bila argumen dimulai `/`, input itu
diperlakukan sebagai command game, bukan chat: `/join <map>` menjadi
`%xt%zm%cmd%1%tfer%<user>%<map>%`. `/goto <nama>` mengikuti dua jalur
client asli: bila target ada di snapshot area lokal dan beda cell, bot mengirim
`moveToCell` ke cell/pad target; bila target tidak ada di area lokal, bot memakai
`%xt%zm%cmd%1%goto%<nama>%` (huruf kecil). Nama pemain yang mengandung spasi
tetap satu argumen. `/afk` memakai extension `afk` room 1, `/rest` memakai
`emotea rest`, dan `/pull`/command `cmd` terverifikasi memakai room 1.
Slash-command yang hanya bekerja di UI client atau belum didukung ditolak dengan
error, jadi tidak pernah bocor sebagai bubble chat atau paket tebakan.

`.capture on` menulis event combat
struktural ke `combat_capture.log` dan tidak menyimpan isi chat. Ejaan lama
`farm ...` masih diterima sebagai kompatibilitas. Umum tersedia: chat, status,
debug, quit.

## Keamanan kredensial

- Password tidak pernah dicetak ke layar atau log.
- Disimpan terenkripsi dengan Windows DPAPI (CryptProtectData), terikat ke
  akun Windows pengguna -> file tidak bisa didekripsi di mesin lain.
- Fallback Fernet+PBKDF2 untuk non-Windows.
- Lokasi: %LOCALAPPDATA%\skua-lite\accounts.enc

## Pilihan cara menyimpan akun (multi vs terenkripsi)

Ada dua cara menyimpan akun. Pilih satu sesuai kebutuhan:

**A. Otomatis terenkripsi (default, 1 akun atau tambah bertahap)**

- Tambah akun bertahap via menu startup `+ Tambah akun` atau
  di terminal farming: `.tambahakun <username>,<password>`
- Kelola via `.editakun <username>,<password>` dan `.hapusakun <username>`.
- `.daftarakun` menampilkan username yang tersimpan (password tidak ditampilkan).
- Cocok untuk menyimpan satu akun atau menambah akun satu per satu.

**B. File `akun.txt` lokal terbuka (banyak akun sekaligus, multi-bot)**

- Buat file `akun.txt` di folder data lokal
  (`%LOCALAPPDATA%\skua-lite\akun.txt`).
- Isi satu baris per akun dengan format `username,password`:
  `mele,password321`
  `sorani ex,password123`
- Baris kosong dan baris komentar `# ...` diabaikan.
- Awal baris boleh berupa indeks seperti `1. ` (terbuang otomatis).
- File ini diabaikan oleh Git dan dibatasi izin hanya pemilik OS
  (Windows ACL / POSIX 0600, best-effort).
- Saat startup MODE FARMING, cukup pilih `Multi-bot` lalu pilih akun
  (`1,3`, `semua`, atau `all`) untuk login sekaligus.

Kedua sumber digabung berdasarkan username dan ditampilkan satu kali.
Jika username sama ada di kedua tempat, entri **terenkripsi menang**.
Penghapusan (`.hapusakun` / `remove_account`) menghapus dari kedua sumber.

## Struktur

    src/skua_lite/
        __main__.py     # CLI entry (argparse)
        config.py       # konstanta protokol/endpoint
        credentials.py  # storage kredensial (DPAPI)
        login.py        # HTTP login -> sToken
        servers.py      # daftar server & pemilihan Yorumi
        sfs.py          # framing + builder/parser paket SmartFox
        mode.py         # pilihan startup AI ASISTEN / FARMING
        farming.py      # runtime farming headless + paket Skua portable
        combat.py       # state class/skill/monster + loop GAR auto-attack
        class_profiles/ # profil rotasi per class (awal: Mage)
        ai_router.py    # toggle/trigger chat + OpenAI-compatible generator
        research.py     # AQW Wiki via Bing + Wayback + cache lokal
        aqw_knowledge.py# glosarium class/enhancement auto-loaded
        ultra_guide.py  # loader & retrieval panduan ultra boss (*.md)
        client.py       # TCP client (poll non-blok, antrian paket)
        bot.py          # state machine: login -> join -> active/afk
        follow.py       # mode `Ikuti aku`: salin gerak owner + goto saat keluar
        area_state.py     # snapshot area dinamis, generation, provenance wire
        area_replay.py    # replay offline capture tersanitasi + expected snapshot
        map_cells.py      # scan label frame SWF untuk daftar cell lengkap
        combat.py       # state combat + attack/respawn/moveToCell
        cli.py          # menu asisten + menu farming + minimize konsol
        runner.py       # pemisah flow mode + auto-relogin watcher
        admin_commands.py # perintah `!` khusus pemilik (Admin Mode)
        agent_tools.py  # aksi nyata: cari web, exec, self-upgrade + verifikasi
    tests/              # 281 unit & integration test (mock, tanpa internet)
    agent/              # AGENT.md + SKILL.md + HEARTBEAT.md + README.md
    panduan/            # knowledge lokal (auto-discover, hot-reload)

## Menjalankan

Windows:

    JALANKAN_SKUA_LITE.bat

Linux:

    chmod +x JALANKAN_SKUA_LITE.sh
    ./JALANKAN_SKUA_LITE.sh

macOS (Terminal atau klik file `.command` di Finder):

    chmod +x JALANKAN_SKUA_LITE.sh JALANKAN_SKUA_LITE.command
    ./JALANKAN_SKUA_LITE.command

Jalankan mode tertentu tanpa prompt (semua OS meneruskan argumen yang sama):

    ./JALANKAN_SKUA_LITE.sh --mode assistant --server Yorumi
    ./JALANKAN_SKUA_LITE.sh --mode farming --server Yorumi --map lair-100000

Cara manual tanpa launcher:

    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -e .
    python -m skua_lite

## Test

    python -m pytest tests/ -v

## Router chat AI (opsional)

Isi konfigurasi endpoint OpenAI-compatible di file:

    C:\Users\reswa\projects\skua-lite\.env

Template isinya:

    SKUA_AI_BASE_URL=https://provider.example/v1
    SKUA_AI_API_KEY=your-key
    SKUA_AI_MODEL=your-model
    SKUA_AI_TIMEOUT=20

File dibaca otomatis saat bot dijalankan dari folder project; environment sistem
masih dapat mengoverride nilainya. `/chat/completions` ditambahkan otomatis jika
belum ada. Router default OFF.

Akun pemilik adalah nama exact `MELE` atau `ME LE`. UID historis (`21623`, `21943`, `21631`,
`22422`) tetap didukung, tetapi karena UID SmartFox dapat berubah saat login ulang, bot juga
mengenali nama exact dari paket `uER` dan mengunci ke UID sesi terbaru. `SORANI EX` tidak termasuk.
Saat pemilik masuk room, bot mengirim `retrieveUserData`, memaksa AI ON, menyapa `Master`
sekali, lalu mengaktifkan Admin Mode. Selama Admin Mode, hanya chat dari UID pemilik aktif
yang dilayani. Sebutan `Master` hanya untuk
sapaan kedatangan pemilik. Setelah `MODE NORMAL`, balasan ke pemilik memakai nada
`bro` dan tidak lagi memakai `Master`/`Tuan`. Balasan ke pemain lain tidak boleh mengandung
kata `Master`/`Tuan`. Jawab singkat sesuai pertanyaan, tanpa basa-basi. Pemilik dapat mengirim
persis `MODE NORMAL` untuk membuka lock sambil mempertahankan AI ON **dan Admin Mode**.
Pemilik dapat mengirim perintah admin khusus pemilik lewat prefix `!`
(hanya UID/nama pemilik aktif yang dieksekusi; pemain lain diabaikan):
Selain itu tersedia perintah follow biasa `Ikuti aku` (mengikuti owner)
atau `Ikuti <nick>` (mengikuti pemain yang dipilih owner). Bot menyalin
gerak cell/koordinat target; saat target keluar area/map, bot otomatis
`/goto <target>` lalu melanjutkan mirroring saat update target masuk lagi.
Perintah `Berhenti` menghentikan follow, mengembalikan bot ke map/cell/
koordinat awal, lalu mengaktifkan AFK.

    !cari <query>     -> riset web umum via hermes agent (tidak terbatas AQW)
    !join <map>       -> pindah map/room, misal `!join yulgar`
    !move <x> <y>     -> jalan ke koordinat, misal `!move 850 302`
    !status           -> state bot, map, room, AFK
    !bantuan          -> daftar perintah admin
    !upgrade <tujuan> -> dua langkah: tanya dulu (`!upgrade ok` untuk eksekusi);
                         agent mengedit project, lalu pytest harus lulus dan daftar
                         file yang diubah dilog sebagai bukti
    !exec <kode>      -> jalankan snippet Python singkat di folder project
                         (API key tidak diteruskan ke child process)
    !run <perintah>   -> perintah allowlist baca-saja; default MATI
                         (aktifkan via `SKUA_ADMIN_SHELL=1` bila perlu)
    !admin off        -> matikan Admin Mode, AI chat tetap ON

Paket `userGone`
atau `exitArea` untuk UID pemilik menghapus lock dan mengembalikan AI ke kondisi awal OFF.
Bot menyimpan maksimal 400 event chat, masuk, dan keluar selama berada di room. Saat pemilik
bertanya, ringkasan log itu disertakan agar AI dapat merangkum topik dan pergerakan pemain
berdasarkan data yang benar-benar tercatat; pemain lain tidak menerima konteks log tersebut.

Panduan lokal Ultra Boss AQW di `panduan/**/*.md` dibaca otomatis saat bot start dan di-reload
otomatis saat file bertambah atau berubah. Saat ada yang bertanya tentang ultra (Dage, Darkon,
Nulgath, Speaker, Gramiel, Grim Challenge, atau mekanik/class/consumable-nya), bot menyisipkan
potongan panduan yang relevan ke prompt dan menjawab berdasarkan fakta panduan itu. Nama file
sumber tidak ditampilkan di chat (batas 150 karakter); jawaban hanya mengutip isi panduan.

Konteks panduan dibatasi hingga ~7000 karakter (maks 10 bagian per boss) sehingga model
mendapat potongan setup, party composition, dan mekanik sekaligus tanpa meledakkan prompt. Timeout
default dinaikkan ke 60 detik dan batas token jawaban ke 500 supaya model punya ruang "berfikir"
lebih lama sebelum merangkum ke 150 karakter balasan AQW.

Setiap pemain memiliki memori percakapan per-orang (12 turn terakhir, maks 40 pemain) yang
disimpan ke `%LOCALAPPDATA%\skua-lite\ai_memory.json`, sehingga pertanyaan lanjutan seperti
"tadi gua bilang apa?" masih bisa dijawab walau bot sempat restart.

Jika jawaban AQW belum tersedia di konteks lokal, model dapat meminta satu putaran riset lewat
marker internal `RESEARCH:`. Bot mencari halaman AQW Wiki, mencoba URL/slug langsung, memakai
Wayback saat Wikidot timeout, lalu menyimpan teks ke `%LOCALAPPDATA%\skua-lite
esearch_cache\`.
Marker, URL, nama file, dan sumber internal tidak pernah diteruskan ke chat. Lihat `agent/README.md`,
`agent/AGENT.md`, `agent/SKILL.md`, dan `agent/HEARTBEAT.md` untuk kontrak operasi lengkap.

Tanpa Admin Mode, ketik persis `MELE AI ON`/`MELE AI OFF` untuk mengatur router.
Saat ON, pesan yang menyebut kata utuh `mel`, `le`, atau `mele` dijawab. Chat akun
bot sendiri diabaikan. Balasan selalu berupa chat biasa, maksimal 150 karakter,
tanpa akses action, dan profanity umum disensor. Pemain non-pemilik yang masuk
room disapa sekali dengan "Halo, <nama>!" (langsung, tanpa AI, dan tidak menyebut
Master/Tuan); pemilik disapa via sapaan AI saat lock aktif.

## Auto-relogin

ReloginWatcher memantau state bot tiap 5 detik. Bila koneksi terputus
(DISCONNECTED_BY_SERVER), bot login ulang memakai kredensial tersimpan dan
otomatis join kembali ke map aktif terakhir. Retry memakai exponential backoff
terbatas (default 5 kali; 2, 4, 8, 16, 32 detik) supaya tidak menghajar server
tanpa henti. Setelah tersambung, target follow dan auto-goal aktif dipulihkan.

## Roadmap berikutnya

- Quest accept & turn-in otomatis
- Multi-akun
- Log chat masuk ke file
