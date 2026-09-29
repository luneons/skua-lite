# RENCANA INDUK — Area Intelligence skua-lite

Status: dokumen kerja (bukan klaim selesai).
Ruang lingkup: menjadikan skua-lite bot headless yang **benar-benar mengenali area** sebelum menambah fitur permainan apa pun.
Dasar: source client AQW (`World.as`, `Game.as`) + audit read-only Grimlite 1.3 + Skua 1.4.4 + kondisi kode skua-lite saat ini.

Aturan dokumen ini:

- Setiap klaim teknis punya rujukan `berkas:baris`.
- Yang belum diuji pada data nyata ditandai `[PERLU VERIFIKASI]`.
- Yang berasal dari analisis (bukan pengamatan langsung) ditandai `[INFERENSI]`.
- Nomor tag SWF ditandai `[INFERENSI]` sampai terbukti pada satu map nyata.

Revisi 2 — hasil fact-check. Perubahan besar dari revisi 1: urutan fase diubah menjadi *vertical slice* (state dinamis dan pergerakan lebih dulu, parsing aset agresif belakangan), setiap exit punya status kepercayaan, dan semua data dinamis dikeluarkan dari `MapTopology` statis.

---

## 0. Prinsip

1. **Dua sumber, bukan satu.** Topologi statis dari aset map; keadaan hidup dari paket server. Tidak ada yang menggantikan yang lain.
2. **Tidak mengarang.** Nilai tanpa asal ditulis `unknown` dan **tidak boleh** memicu aksi otomatis.
3. **Hanya nilai terverifikasi boleh dieksekusi.** Exit/route/pad harus berstatus `verified` sebelum dipakai planner.
4. **Nama perintah bukan bukti.** `AttackMonster`, `Jump`, `UseSkill`, `GetCells` di Grimlite adalah fungsi Flash ter-inject, bukan format paket.
5. **Verifikasi, bukan delay.** Setelah aksi, tunggu perubahan state dari server.
6. **Setiap nilai punya provenance**: `asset` | `wire` | `inferred` | `unknown`.
7. **Bukti di berkas.** Setiap kemampuan baru punya capture/report di `docs/evidence/area/`.
8. **TDD.** Test merah dulu (aturan repo).

---

## 1. Temuan terverifikasi

### 1.1 Cara client mengenali area

| Bukti | Rujukan |
|---|---|
| `cellSetup` memindai display list: `hasPads`, `isEvent`, `isSolid`, `isMonster`, `isProp` | `World.as:3540-3704` |
| Event tanpa properti di luar daftar → `arrEvent` | `World.as:3605`, `3625-3627` |
| Object prop-event → `arrEvent` | `World.as:3682-3685` |
| Object solid → `arrSolid` | `World.as:3609`, `3617-3619` |
| Object monster → dipetakan ke `MonMapID` | `World.as:3631-3676` |
| `arrEvent`/`arrSolid` direset saat keluar cell | `World.as:2297-2310`; jalur cleanup `2381-2386` |
| Pad = nama instance di `this.map`, diambil via `map[strPad]` | `World.as:6090-6092` |
| Default spawn `Enter`/`Spawn` | `World.as:4139-4142` |
| `onMapLoadComplete` → `initMonsters(mondef, monmap)` | `World.as:2169-2188` |
| Masuk map: cell/pad diri dari `uoTree` → `moveToCell` | `World.as:2206-2222` |
| Portal dikenali dari `strSpawnCell` / `tCell` | `World.as:8487` |
| `moveToCell` kirim `sendXtMessage("zm","moveToCell",[cell,pad],"str",curRoom)` | `World.as:2841-2885`, kirim di `2884` |
| **Argumen ketiga `true` → paket TIDAK dikirim** (murni lokal) | `World.as:2882-2885` |
| `mtcid` dari server → `moveToCellByIDb` cocokkan `tID` / nama `ia<N>` → `moveToCell(...,true,true)` | `World.as:2917-2926` + `Game.as:1616-1622` |
| `eventUpdate` dikirim ke map | `World.as:3254-3257` (simpan), `3259-3275` (kirim + bersihkan) |
| Jalur event kedua: `pendingMapEvents` / `eventTrigger` | `World.as:2441-2460` |
| Filename aset map dari server | `Game.as:2162` (`resObj.strMapFileName`), `2215-2216` (`loadMap`) |
| `reloadmap` memakai key berbeda: `resObj.sFileName` | `Game.as:1920` |
| Client pakai path relatif; nilai yang memuat `cdn.aq.com` dipakai apa adanya sebagai URL absolut | `World.as:2054-2059` |
| `moveToArea` mengisi `uoBranch`→`uoTree`, `monBranch`→`monTree[MonMapID]` | `Game.as:2024-2052`, `2053-2080` |
| `event` → `setMapEvents`, `cellMap` → `setCellMap` | `Game.as:2081-2088`, `2089-2096` |

Catatan penting: **nama berkas map wajib dari server** (`strMapFileName`), dan client sendiri menerima URL absolut. Jadi origin unduhan bukan konstanta tetap.

### 1.2 Sumber URL aset (Skua 1.4.4 — bukan Grimlite)

| Bukti | Rujukan |
|---|---|
| `https://game.aq.com/game/gamefiles/maps/{FilePath}` | `Skua.Core/Scripts/ScriptMap.cs:320` |
| `Map.FilePath = data.strMapFileName` | `Skua.Core/Scripts/ScriptInterface.cs:450` |

Pencarian di pohon Grimlite untuk `gamefiles/maps` / `strMapFileName` menghasilkan 0 kecocokan. Jadi konvensi origin itu milik Skua; skua-lite mengadopsinya sebagai konfigurasi yang bisa diubah, bukan kebenaran tetap.

`[PERLU VERIFIKASI]` Perilaku CDN nyata (host, query versi, nama berkas dengan atau tanpa `.swf`) belum pernah direkam di repositori ini. Wajib direproduksi di Fase 0 dengan log bertanggal. Klaim "404 terbukti" pada revisi 1 **dicabut** karena tidak ada artefak bukti yang tersimpan.

### 1.3 Grimlite 1.3 (read-only, tidak diubah)

**Transport:** tidak punya socket game sendiri. Transport adalah Flash ActiveX yang ditanam, digerakkan lewat `ExternalInterface` (`Flash.Call`). Proxy-nya adalah dispatcher/forwarder MITM, bukan pemilik socket.

| Bukti | Rujukan |
|---|---|
| `AxShockwaveFlash flash` dipakai seluruh botting | `Grimoire.Botting/BotUtilities.cs:1,18` |
| Delegate/jembatan `Flash.Call` | `Grimoire.Tools/Flash.cs:20-28` |
| Player Flash ditanam di form | `Grimoire.UI/Root.cs:196-211` |
| Loop klien | `Grimoire.Networking/Proxy.cs:185` (`ClientExecute`) |
| Registry handler per command | `Proxy.cs:48-107`, `134-155` |
| Dispatcher XT/JSON/XML | `Proxy.cs:129-158` |
| Daftar pad di UI Grimlite (8 buah) | `Grimoire.UI/Root.cs:412-420` |

**Cacat terverifikasi (jangan ditiru):**

| Cacat | Rujukan |
|---|---|
| `text` hasil `Replace("{ROOM_ID}")` dihitung, yang dikirim `data` → placeholder tidak efektif | `Proxy.cs:111` vs `Proxy.cs:115` |
| `catch { }` menelan semua error parser/handler | `Proxy.cs:157` |
| Pickup drop memakai `Task.Delay` tanpa `await` | `Bot.cs:382`, `387`, `395` |
| Plugin dimuat via `Assembly.LoadFile` tanpa validasi | `GrimoirePlugin.cs:59` |
| `AutoBuyBack` mengirim kredensial lewat POST HTTP lama | `Grimoire.Tools.Buyback/AutoBuyBack.cs:16-18`, `36` |

Catatan: klaim "Grimlite membekukan jam sistem" **tidak ditemukan** di pohon 1.3 dan dihapus dari daftar.

**Yang berguna dari Grimlite** (desain, bukan wire): registry handler, loop command berindeks dengan label/goto/variabel/conditional, quest accept→farm→complete→reaccept, manajemen drop/whitelist, kondisi HP/MP per skill, auto-rest, profil tersimpan, dan pola tunggu-state (`WaitUntil`, `BotUtilities.cs:20`).

**Yang tidak dipakai:** semua `Flash.Call` yang bergantung SWF modifikasi (infinite range, enemy magnet, provoke, cancel target, `SendClientPacket`, spoof level/gold/gender), plugin `LoadFile`, `AutoBuyBack`, dan daftar pad hardcode sebagai satu-satunya sumber.

### 1.4 Kondisi skua-lite sekarang

| Bagian | Keadaan | Rujukan |
|---|---|---|
| Parser frame label: tag 43 + 86, FWS + CWS, cache `.map_cache/` | ada | `src/skua_lite/map_cells.py` |
| Cache gagal parse → pakai cache lama; error tulis ditelan | masalah | `map_cells.py:191-202` |
| `known_cells()` / `known_pads()` / `move_to_cell()` + wire asli | ada | `combat.py:422`, `443`, `683` |
| Daftar pad skua-lite 12 nama (8 Grimlite + 4 diagonal) | ekstensi, perlu didokumentasikan | `combat.py:29-32` |
| Scan aset di thread terpisah | ada | `farming.py:92-125` |
| Reducer state wire (AreaState) | **belum ada** | — |
| State machine pergerakan | **belum ada** | — |

Yang sudah ada baru "daftar cell + daftar pad". Belum ada model area.

---

## 2. Batas tegas: dari aset vs dari wire

### 2.1 Langsung dari tag statis (dapat diandalkan begitu parser benar)

1. Daftar lengkap cell (frame label: tag 43, tag 86).
2. Nama instance per frame dan posisinya (PlaceObject2 tag 26 / PlaceObject3 tag 70).
3. Transform/scale instance (matriks) → koordinat relatif panggung.
4. Bentuk/bounding shape (DefineShape) — geometry kasar.

`[INFERENSI]` Nomor tag di atas belum diuji pada map SWF nyata dalam proyek ini.

### 2.2 Hanya lewat bytecode/heuristik → WAJIB `inferred` sampai diverifikasi

`tCell`, `tPad`, `strSpawnCell`, `tID`, `isEvent`, `isMonster`, `MonMapID`, `isSolid`, `isProp` **bukan** properti statis. Itu properti runtime yang dipasang script frame; pengamatan di client terjadi saat `cellSetup`/`padHit` berjalan (`World.as:3599-3684`, `8487`).

Konsekuensi:

- Pemindaian literal bytecode (`DoAction` 12, `DoInitAction` 59, `DoABC` 82 `[INFERENSI]`) hanya boleh menghasilkan **kandidat**.
- `SymbolClass` (tag 76) memetakan characterId→class, **tidak** menetapkan nilai properti instance. Tidak boleh dipakai untuk menyimpulkan exit.
- Asosiasi nilai ke instance wajib konservatif; kalau tidak yakin, `unknown`.

### 2.3 Tidak mungkin dari aset (wajib wire)

1. Monster hidup sekarang: HP, `intState`, `MonMapID` aktif, respawn.
2. Pemain di room: nama, UID, cell, pad, HP/MP, state.
3. Room ID, area ID, private room, jumlah pemain.
4. Class & kemampuan aktual: cooldown, biaya, tipe target, unlock.
5. Aura, target, hasil combat, drop.
6. Lock dinamis (quest/kill-count/item/event) yang membatalkan exit yang ada di aset.
7. Object yang dibuat dinamis oleh `event` / `cellMap` server.

### 2.4 Kesimpulan

Scanner area = **topologi aset (statis, immutable)** + **state wire (dinamis, berversi generasi area)**. Keduanya wajib dan disimpan terpisah.

---

## 3. Arsitektur target

```
 aset SWF  ->  SwfMapReader  ->  MapTopology (immutable, tanpa state hidup)
                                         \
 wire      ->  AreaStateReducers  -------- > WorldModel (provenance per field)
                                              |
                                              v
                                      PolicyEngine (satu tujuan per milestone)
                                              |
                                              v
                              ActionSender (paket asli) + MoveStateMachine
```

### 3.1 Kontrak data

```python
# ---------- statis (immutable) ----------
@dataclass(frozen=True)
class PadInfo:
    name: str; x: float; y: float; frame: str; depth: int

@dataclass(frozen=True)
class ExitCandidate:          # selalu mulai sebagai kandidat, TIDAK executable
    name: str; frame: str; cell: str; pad: str
    status: str               # "candidate" | "unverified" | "verified"
    evidence: str             # berkas:baris atau id capture
    verified_at: str | None

@dataclass
class MapTopology:
    file_name: str; checksum: str; parser_version: str
    frames: tuple[str, ...]
    pads: dict[str, tuple[PadInfo, ...]]        # frame -> pad
    instances: dict[str, tuple[Instance, ...]]  # simpan depth + path
    exits: tuple[ExitCandidate, ...]            # default: candidate
    unsupported: tuple[str, ...]                # tag/struktur tak dikenali
```

```python
# ---------- dinamis (berversi generasi area) ----------
@dataclass
class SelfState:    cell: str | None; pad: str | None; hp: int | None; state: int | None
@dataclass
class PlayerState:  name: str; uid: int; cell: str; pad: str; hp: int | None
@dataclass
class MonsterState: map_id: int; mon_id: int | None; name: str
                    hp: int; max_hp: int | None; cell: str | None; state: int

@dataclass
class AreaState:
    generation: int                 # naik setiap moveToArea
    room_id: int | None
    map_name: str | None; map_file: str | None
    self_state: SelfState | None
    players: dict[str, PlayerState]
    monsters: dict[int, MonsterState]
    map_events: tuple[dict, ...]    # dari wire, BUKAN dari aset
    cell_map: dict | None
    observed_at: float
```

```python
# ---------- gabungan ----------
@dataclass(frozen=True)
class Value:
    value: object
    source: str        # asset | wire | inferred | unknown
    at: float
    generation: int | None
    executable: bool   # True hanya bila source terverifikasi dan masih segar

class WorldModel:
    def cells(self) -> list[Value]                       # asset ∪ wire
    def exits_from(self, cell: str, *, only_verified=True) -> list[ExitCandidate]
    def targets(self, name: str | None = None, cell: str | None = None) -> list[MonsterState]
    def path(self, start: str, goal: str) -> list[tuple[str, str]] | None   # edge verified saja
    def unknown(self) -> list[tuple[str, str]]           # field -> alasan
    def conflicts(self) -> list[tuple[str, str, str]]    # field, nilai asset, nilai wire
```

Aturan presedensi konflik (**per field**, bukan per baris):

| Field | Menang | Alasan |
|---|---|---|
| `frames`/`pads`/`instances` | `asset` | wire tidak tahu seluruh topologi |
| `self`/`players`/`monsters`/`room`/`class` | `wire` | aset tidak punya keadaan hidup |
| `map_events`/`cell_map` | `wire` | dinamis dari server |
| `exits` | `verified` > `asset` | status verifikasi mengikat |

Aturan kesegaran: nilai `wire` yang `generation`-nya bukan generasi aktif **tidak boleh** dieksekusi.

### 3.2 Status implementasi saat ini (jujur, per revisi ini)

Sudah ada dan diuji:

- `AreaStateStore`: `moveToArea` menaikkan generation dan atomik mengganti
  self/pemain/monster/event/cellMap; incremental `mtls`/`uotls`/`respawnMon`
  memperbarui generation aktif. Paket yang dibubuhi generation lama ditolak.
- Snapshot copy-safe untuk pembaca concurrent, laporan `.area`, dan JSON
  deterministik schema v1 lewat `.area json`.
- Replay offline berversi dari `manifest.json` + `events.jsonl` +
  `expected_area.json`; fixture bawaan sintetis dan tanpa rahasia/chat.
- Goal tingkat tinggi `lawan semua musuh yang ada di map ini` (kalimat natural)
  atau `.goal map`, plus `.goal stop`.
- Engine, saat goal aktif: lawan semua monster hidup di cell aktif → pilih
  cell lain yang **masih punya monster hidup** dari snapshot server → kirim
  `%xt%zm%moveToCell%<curRoom>%<cell>%<pad>%` → tunggu konfirmasi posisi dari
  `uotls`/`moveToArea` → lanjut lawan.
- Verifikasi perpindahan, bukan sleep: `move_timeout` 2 detik, satu retry
  terbatas, cell gagal diblokir (`blocked_cells`) dan dilaporkan.
- Status mesin: `requested` / `retried` / `confirmed` / `failed` pada
  `.combat` dan `.goal`.
- Pemuatan ulang: `map_events`/`cell_map` tetap hanya dari wire.

Belum ada (tetap roadmap, jangan diklaim selesai):

- Graf exit SWF terverifikasi (status `candidate`/`unverified`/`verified`).
- Penggabungan topologi SWF ke `WorldModel` dengan provenance asset/conflict.
- Rute multi-hop di atas edge terverifikasi (Fase 7).

Artinya navigasi otomatis saat ini **satu-hop dan berbasis bukti server**
(cell monster yang teramati), bukan pathfinding graf penuh.

---

## 4. Roadmap (vertical slice lebih dulu)

Setiap fase punya **deliverable**, **kriteria penerimaan**, dan **gate**. Gagal gate = jangan lanjut.

Korpus yang didukung didefinisikan eksplisit, bukan "tiga map":

- kompresi: FWS/CWS (ZWS `[PERLU VERIFIKASI]`),
- generasi ActionScript: AS1/AS2 dan AS3-ABC,
- kompleksitas: jumlah frame, jumlah instance per frame,
- perilaku: map statis vs map dengan event dinamis.

---

### Fase 0 — Scope, fixture, dan replay harness

Deliverable:

- Capture paket nyata tersanitasi di `docs/evidence/area/` beserta manifest.
- `.probe map`: buang `strMapFileName`, `strMapName`, `room_id`, cell & pad teramati.
- Skema capture berversi + skema snapshot hasil.

Kriteria penerimaan:

- Capture memuat transisi lengkap: `moveToArea`, `uotls` relevan, `monBranch`, `event`, `cellMap`, batas disconnect.
- Manifest memuat: waktu, map file, checksum, versi skema, snapshot akhir yang diharapkan.
- Kredensial, token sesi, dan chat **diredaksi**.
- `strMapFileName` valid → unduhan HTTP sukses + signature SWF cocok + checksum cocok.
- Satu perintah offline me-replay corpus secara deterministik.

Gate: replay dari checkout bersih menghasilkan snapshot identik.

---

### Fase 1 — AreaState dinamis (wire)

Deliverable:

- Reducer paket → snapshot area atomik berversi.
- Siklus hidup generasi area (naik tiap `moveToArea`).
- Output diagnostik mode wire-only.

Kriteria penerimaan:

- Replay menghasilkan state self/room/players/monsters/event dengan **tepat**.
- Pergantian generasi menghapus semua entitas area lama.
- Paket duplikat, terlambat, dan tidak berurutan tidak menghidupkan entitas lama.
- Field opsional yang hilang tetap `unknown` (bukan default yang memicu aksi).
- Pembaca melihat snapshot atomik saat receiver dan scanner aset jalan bersamaan.

Gate: test replay + test state basi/out-of-order lulus.

---

### Fase 2 — State machine pergerakan

Deliverable:

- Status eksplisit: `requested → acknowledged → confirmed | timed_out | retried | failed`.
- Timeout, pembatalan, retry terbatas, bukti terstruktur.

Kriteria penerimaan:

- Test menutup: sukses, ditolak, timeout, disconnect, konfirmasi terlambat, konfirmasi ganda, retry setelah state berubah.
- Sebelum retry, state diperiksa ulang (mencegah perpindahan ganda).
- Laporan sukses **selalu** menyertakan cell tujuan dan generasi area yang cocok.
- Gate live: minimal 5 edge terarah berbeda di beberapa map (bukan 20 kali edge sama).
- Nol "sukses palsu"; retry terbatas; tanpa pemulihan manual.

Gate: test fault-injection + perpindahan live terkendali lulus.

---

### Fase 3 — Topologi aset minimal

Deliverable:

- Pengunduh + cache aman (checksum, ukuran maksimum, degradasi bila gagal).
- Frame label **dan** pad dari display list (PlaceObject) untuk korpus.

Kriteria penerimaan:

- Test emas memeriksa label frame, instance, depth, transform, dan penghapusan (RemoveObject/RemoveObject2) — bukan sekadar "Spawn ada".
- Display list bersifat inkremental: perubahan boleh menghilangkan characterId/nama/matriks; objek bisa dihapus dan dipakai ulang per depth. Instance tidak boleh diindeks hanya dengan nama.
- Semua cell yang teramati di wire **harus** ada di hasil parse; selisih wajib diselidiki.
- Konversi twips→pixel, batas panggung, label duplikat, nama duplikat punya test.
- Tag tak dikenal → hasil `unsupported` terstruktur, tidak crash.
- SWF rusak / decompress bomb → gagal dengan aman (batas ukuran & waktu).

Gate: test topologi emas lulus; data tak didukung terdegradasi dengan aman.

---

### Fase 4 — WorldModel + `.area`

Deliverable:

- Gabungan topologi immutable + snapshot dinamis.
- `.area` (manusiawi) dan `.area json` (mesin, skema berversi).
- Laporan `unknown` dan `conflicts`.

Kriteria penerimaan:

- `.area json` tervalidasi terhadap skema yang ikut di-commit, deterministik.
- **Setiap nilai** (bukan hanya tiap baris) membawa provenance + kesegaran.
- Konflik asset vs wire ditampilkan eksplisit dan tidak pernah otomatis executable.
- Mode wire-only dan asset-only diuji dan melaporkan kemampuan yang hilang.
- Perintah tidak melakukan I/O jaringan/disk di jalur receiver paket.

Gate: test snapshot lulus pada mode normal, asset-only, wire-only, dan konflik.

---

### Fase 5 — Ekstraksi exit konservatif + verifikasi

Deliverable:

- Kandidat exit dengan bukti; status per edge: `candidate`/`unverified`/`verified`.
- Verifikasi live opt-in yang mencatat hasil server (termasuk penolakan/lock).

Kriteria penerimaan:

- Setiap exit mencatat: sumber, status, cell asal, cell+pad tujuan, bukti ekstraksi, waktu verifikasi terakhir.
- Hanya exit `verified` yang boleh masuk rute otomatis.
- Map emas: **nol** false-executable; exit tak dikenali dilaporkan `unknown`.
- Verifikasi live dimulai dari state yang dideklarasikan dan mengonfirmasi cell tujuan **dan** generasi area.
- Edge maju dan traversal balik diuji terpisah.
- Ekstraksi literal bytecode hanya menghasilkan kandidat.

Gate: satu map terpilih punya himpunan edge verified lengkap dan nol edge palsu.

---

### Fase 6 — Vertical slice MVP (satu tujuan)

Deliverable:

- Satu kebijakan: `farm_target` — cari target → pindah (satu hop, edge verified) → serang → konfirmasi mati → kembali.

Kriteria penerimaan:

- Target awalnya **di luar** cell saat ini dan ditemukan dari state hidup, bukan dari room hardcode.
- Rute hanya berisi edge `verified`.
- Setiap langkah terkonfirmasi server: perpindahan, pemilihan target, mulai serang, target mati/hilang, kembali.
- Jalur aman untuk: tanpa target, target respawn, pemain mati, disconnect, lock dinamis, dan perintah stop — semua dalam batas aksi (bounded).
- Minimal 10 siklus berturut-turut tanpa intervensi manual, dengan trace tersimpan.

Gate: 10 siklus lulus tanpa pemulihan manual.

---

### Fase 7 — Travel umum

Deliverable:

- BFS di atas edge verified, penanganan lock dinamis, beberapa map, dukungan SWF lebih luas.

Kriteria penerimaan:

- Matriks rute multi-hop lulus replay dan live terkendali.
- Rute gagal → jatuh ke status aman, bukan tebak-tebakan.

Gate: matriks rute lulus.

---

### Fase 8 — Hardening & observability

Deliverable:

- Batas performa, perilaku reconnect, invalidasi cache, metrik, laporan, test input rusak.
- Perbaikan bug cache: `map_cells.py:191-202` tidak boleh diam-diam memakai cache basi.

Kriteria penerimaan:

- Kunci cache = nama map + checksum + versi parser + versi skema; entri rusak ditolak.
- Rumus & penyebut metrik didefinisikan (akurasi exit, latensi pindah, rasio retry, rasio stuck).
- Anggaran terukur: waktu parse dingin, latensi `.area` hangat, latensi handler receiver, memori, ukuran decompress maksimum.
- Suite offline penuh lulus dari checkout bersih dengan satu perintah terdokumentasi.

Gate: laporan bukti memenuhi ambang reliabilitas & latensi yang dipublikasikan.

---

### Fase 9 — Spikes opsional (go/no-go)

- Slot monster dari aset (`isMonster` + `MonMapID`) — hanya bila planner butuh.
- Geometry/walkable (`isSolid`, bounding shape) — hanya bila planner butuh.

Kriteria: setiap spike punya target akurasi terukur + keputusan go/no-go; tidak boleh memblokir MVP.

Gate: konsumen bernama ada dan terbukti untung.

---

### Fase 10 — Fitur tingkat lanjut (inkremental)

Follow player, quest (accept→farm→complete→reaccept), drop/whitelist, shop, bank, boost, profil perilaku JSON.

Kriteria per fitur: test replay, bukti live, aksi terbatas, dan persetujuan eksplisit untuk aksi destruktif (beli/jual/hapus).

Gate: per fitur, bukan sekaligus.

---

## 5. Keputusan jalur

| Keputusan | Alasan |
|---|---|
| Hybrid aset + wire | Aset tidak tahu keadaan hidup; wire tidak tahu topologi. |
| State dinamis sebelum parsing aset agresif | Vertical slice lebih cepat berguna & mudah diuji |
| Perpindahan terverifikasi sebelum exit/policy | Semua verifikasi live bergantung padanya |
| Nama map dari server, origin dari config | Client menerima URL absolut (`World.as:2056`) |
| Exit punya status kepercayaan | Mencegah tebakan jadi rute otomatis |
| `map_events`/`cell_map` hanya dari wire | Itu data dinamis server |
| Registry handler (pola `Proxy.cs:134-155`) | Lebih mudah diuji daripada if-chain |
| Verifikasi state, bukan delay | Akar stuck pada kasus respawn sebelumnya |
| Cache berversi + checksum | Mencegah aksi berdasarkan topologi basi |
| TDD + capture sebagai bukti | Aturan repo, sudah menangkap bug nyata |

**Tidak akan dilakukan:** spoofing client (`SendClientPacket`, level/gold/gender), plugin `Assembly.LoadFile`, `AutoBuyBack`, packet spam, aksi beli/jual otomatis tanpa perintah, dan daftar pad hardcode sebagai satu-satunya sumber.

---

## 6. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Aset map tak bisa diunduh | Scan aset mati | Mode degradasi wire-only, ditandai parsial |
| SWF AS3/ABC | Ekstraksi literal gagal | Kandidat nol, tetap `unknown`; tidak ada tebakan |
| Bytecode tak bisa diasosiasikan ke instance | Exit salah | Status kandidat; verifikasi live wajib |
| Object dibuat dinamis server | Topologi tak lengkap | Gabungkan `event`/`cellMap`; sisanya `unknown` |
| Map besar | Parser lambat/memori | Cache JSON per frame + batas ukuran + lazy |
| SWF adversarial (decompress bomb) | Crash/hang | Batas decompress, timeout, test input rusak |
| Race receiver vs scanner | State campur generasi | Snapshot atomik + `generation` |
| Lock dinamis | Edge valid jadi aksi salah | Verifikasi opt-in + penanganan penolakan server |
| Data sensitif di capture | Kebocoran | Redaksi wajib di Fase 0 |
| Scope melebar ke quest/follow | Inti tak pernah stabil | MVP satu tujuan dulu, Fase 10 terpisah |

---

## 7. Definisi selesai

Proyek "mantap" bila semua ini benar **dengan bukti**:

1. `.area` pada map nyata menampilkan cell, pad, exit, monster, pemain, `unknown`, dan `conflicts` — setiap nilai punya provenance.
2. Berpindah cell sendiri menuju target dan kembali: 10 siklus berturut tanpa intervensi, dengan trace.
3. Tidak ada cell/pad/exit/hasil yang muncul tanpa sumber yang bisa ditunjuk.
4. Semua paket yang dikirim punya rujukan call site di client.
5. Setiap exit yang executable berstatus `verified`, nol false-executable.
6. `pytest` hijau; setiap kemampuan baru punya test yang pernah merah.
7. Laporan bukti dari sesi nyata ada di `docs/evidence/area/`.
8. Suite offline lulus dari checkout bersih dengan satu perintah, tanpa Flash.

---

## 8. Langkah berikutnya (paling awal)

1. **Fase 0**: `.probe map` + capture `moveToArea` nyata (ambil `strMapFileName` asli). Sekaligus buktikan perilaku HTTP/CDN-nya, karena `[PERLU VERIFIKASI]` itu memblokir Fase 3.
2. **Fase 1**: reducer AreaState + replay harness (tidak butuh SWF sama sekali).
3. **Fase 2**: state machine pergerakan.
4. Baru **Fase 3/4**: unduh satu SWF nyata, validasi parser, tampilkan `.area`.

Alasan urutan ini: Fase 1 dan 2 bisa dikerjakan penuh tanpa bergantung pada keberhasilan mengunduh SWF, sehingga proyek tetap maju walau jalur aset tersendat.

---

## Lampiran A — Rujukan

**Client AQW** (scratch, hasil decompile):

- `World.as:2054-2059` loadMap + penanganan `cdn.aq.com`
- `World.as:2169-2188` onMapLoadComplete / initMonsters / enterMap
- `World.as:2206-2222` masuk map, `uoTree` → `moveToCell`
- `World.as:2297-2310`, `2381-2386` reset `arrEvent`/`arrSolid`
- `World.as:2441-2460` pendingMapEvents / eventTrigger
- `World.as:2841-2885` `moveToCell`; kirim di `2884`; syarat `param3` di `2882`
- `World.as:2917-2926` `moveToCellByIDb` (jalur `mtcid`)
- `World.as:3254-3257`, `3259-3275` setMapEvents / initMapEvents
- `World.as:3540-3704` `cellSetup`
- `World.as:3599-3684` properti runtime event/solid/monster
- `World.as:4139-4142` resetSpawnPoint
- `World.as:6090-6092` pad = `map[strPad]`
- `World.as:8487` `padHit` (`strSpawnCell`/`tCell`)
- `Game.as:1616-1622` case `mtcid`
- `Game.as:1920` `reloadmap` (`sFileName`)
- `Game.as:2024-2096` moveToArea: uoBranch/monBranch/event/cellMap
- `Game.as:2162`, `2215-2216` `strMapFileName` → loadMap

**Grimlite 1.3** (read-only, tidak diubah):

- `Grimoire.Tools/Flash.cs:20-28` jembatan Flash
- `Grimoire.Botting/BotUtilities.cs:1,18` `AxShockwaveFlash`
- `Grimoire.Networking/Proxy.cs:48-107,134-155` registry handler
- `Grimoire.Networking/Proxy.cs:109-127` SendToServer/SendToClient (cacat `111`/`115`)
- `Grimoire.Networking/Proxy.cs:129-158` dispatcher (catch kosong di `157`)
- `Grimoire.Networking/Proxy.cs:185` ClientExecute
- `Grimoire.UI/Root.cs:196-211` Flash ditanam
- `Grimoire.UI/Root.cs:412-420` daftar pad UI (8)
- `Grimoire.Botting/Bot.cs:382,387,395` Task.Delay tanpa await
- `Grimoire.Tools.Plugins/GrimoirePlugin.cs:59` LoadFile
- `Grimoire.Tools.Buyback/AutoBuyBack.cs:16-18,36` kredensial

**Skua 1.4.4** (read-only, tidak diubah):

- `Skua.Core/Scripts/ScriptMap.cs:320` URL `gamefiles/maps/{FilePath}`
- `Skua.Core/Scripts/ScriptInterface.cs:450` `FilePath = strMapFileName`

**skua-lite:**

- `src/skua_lite/area_state.py` snapshot area dinamis, generation, provenance wire
- `src/skua_lite/area_replay.py` replay fixture tersanitasi dan verifikasi snapshot
- `src/skua_lite/map_cells.py` (tag 43/86, FWS/CWS, cache; bug di `191-202`)
- `src/skua_lite/combat.py:29-32` daftar 12 pad
- `src/skua_lite/combat.py:422,443,683` known_cells / known_pads / move_to_cell
- `src/skua_lite/farming.py:92-125` scan aset thread terpisah

## Lampiran B — Antarmuka perintah

```
.area              ringkasan area + provenance tiap nilai
.area json         keluaran mesin (skema berversi, deterministik)
.mapinfo           file SWF, checksum, versi parser, status cache
.probe map         dump strMapFileName/strMapName/room + sel teramati
.cells             cell (asset ∪ wire) + provenance
.cell <nama> [pad] pindah cell (sudah ada)
.exits [cell]      exit + status (candidate/unverified/verified) + tujuan
.movestate         status state machine pergerakan terakhir
.unknown           daftar hal yang belum diketahui (tidak dipakai otomatis)
.conflicts         nilai yang berbeda antara asset dan wire
```
