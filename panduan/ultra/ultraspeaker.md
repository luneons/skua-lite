# Panduan Ultra Speaker — AQW

> **Ultra Speaker = The First Speaker (Malgor)** di `/join ultraspeaker`.
>
> Panduan ini disusun setelah mengecek dokumentasi AQWorlds resmi, AQWorlds Wiki yang diperbarui, AQWG Ultra Boss guide, serta guide mekanik komunitas yang mendokumentasikan rotation dan zoning.
>
> **Tujuan utama:** memahami mekanik sebelum mencoba DPS. Ultra Speaker adalah fight yang sangat bergantung pada koordinasi 4 pemain; satu kesalahan mekanik dapat menyebabkan seluruh party wipe.

---

# 1. Informasi Dasar

## Boss

**The First Speaker / Malgor**

- Map: `/join ultraspeaker`
- Level: **100**
- HP: **10,000,000**
- Difficulty: **5 stars**
- Respawn: sekitar **30 detik**
- Boss Shield: damage di atas **150,000** per hit terkena diminishing return yang sangat kuat.
- Malgor tidak memiliki tagged race, sehingga racial damage boost tidak menjadi faktor utama.

Sumber:
- AQWorlds Wiki — The First Speaker
- AQWorlds Design Notes — ShadowFlame Ultra Boss

---

# 2. Kenapa Ultra Speaker Sulit?

Ultra Speaker mempunyai tiga mekanik utama yang harus dilakukan bersamaan:

```text
TRUTH
  ↓
LISTEN
  ↓
EQUAL
  ↓
TRUTH
  ↓
LISTEN
  ↓
EQUAL
  ↓
repeat
```

Ketiga kemampuan ini saling berkaitan.

Kesalahan terbesar adalah menganggap ketiganya sebagai serangan biasa.

Sebenarnya:

- **Truth** → harus di-taunt.
- **Listen** → harus di-taunt dan berhubungan dengan stun/petrify.
- **Equal** → pemain harus melakukan zoning satu per satu.
- **Equal** juga menghapus debuff dasar Malgor, tetapi dapat membunuh pemain yang masih membawa debuff tertentu.
- **Equal** menyembuhkan Malgor.

Jadi fight ini adalah gabungan:

```text
TAUNT
+
ZONE
+
CLEANSE
+
DECAY
+
SUPPORT
```

---

# 3. Basic Attack Malgor

Serangan biasa Malgor memberikan beberapa debuff.

## Corruption + Somber

Shadowflame Slash memberikan:

- **Corruption**
- **Somber**

Keduanya:

- durasi sekitar 20 detik
- menurunkan damage dealt
- menurunkan defense
- stack tanpa batas

Selain itu Malgor memberikan:

## Mana Drought

- durasi sekitar 60 detik
- mengurangi Intelligence sekitar 40%

Dalam strategi normal, pemain tidak perlu mencoba mengatasi stack ini secara manual.

**Equal** digunakan untuk membersihkannya.

---

# 4. TRUTH

Malgor memberikan tanda:

> **"I will make you see the truth."**

Skill:

**Magia Draw → Magia Burn**

### Efek utama

Magia Burn memberikan:

> **Magia Burn**

Efeknya meningkatkan **Magic Damage Taken sebesar 300% per stack**.

Durasi sekitar:

**18 detik**

Stack:

**Infinite**

Ini sangat berbahaya.

---

## Apa yang harus dilakukan?

**Truth harus di-taunt.**

Tujuan taunt:

```text
Malgor
  ↓
Truth
  ↓
Taunt
  ↓
Damage debuff diarahkan ke player yang memang bertugas
```

Jangan membiarkan Truth mengenai player secara sembarangan.

---

# 5. LISTEN

Malgor berkata:

> **"You shall listen."**

Skill ini adalah:

**Energy Draw → Stasis Field**

Setelah charge selesai, target terkena:

> **Stasis**

Efek:

- stun/petrify
- sekitar 6 detik

Secara visual, karakter terlihat seperti tidak bisa bergerak.

---

## Listen juga harus di-taunt

Sama seperti Truth:

```text
Truth  → taunt
Listen → taunt
```

Tetapi Listen mempunyai masalah tambahan.

Jika kamu terkena Listen tepat sebelum Equal:

```text
Listen
 ↓
Stasis
 ↓
Equal
 ↓
tidak bisa keluar zone
 ↓
mati
```

Karena itu, pemain perlu memahami timing movement.

---

# 6. EQUAL

Malgor berkata:

> **"All stand equal beneath the eyes of the Eternal."**

Ini adalah mekanik yang paling mudah dikenali secara visual.

Arena akan menampilkan:

```text
┌─────────────────────┐
│                     │
│      RED ZONE       │
│                     │
└─────────────────────┘
```

Equal hanya mengenai pemain yang berada di dalam area tersebut.

---

# 7. Aturan PALING PENTING Equal

## Hanya SATU pemain yang boleh berada di dalam zone.

Jangan:

```text
Player A ─┐
Player B ─┼─ masuk bersamaan
Player C ─┤
```

Lakukan:

```text
Player A
   ↓
masuk zone
   ↓
Equal
   ↓
keluar

Player B
   ↓
masuk zone
   ↓
Equal
   ↓
keluar
```

Dan seterusnya.

---

# 8. Kenapa Harus Bergantian?

Equal memberikan damage yang meningkat untuk setiap pemain berikutnya yang terkena.

AQWorlds Wiki mencatat:

> Equal memberikan **+100% damage pada setiap player berikutnya yang terkena**.

Jadi jika beberapa pemain berada di zone:

```text
Player 1 → damage normal
Player 2 → damage lebih besar
Player 3 → lebih besar lagi
...
```

Secara praktis:

> **Jangan pernah berbagi Equal zone.**

---

# 9. Equal Bisa Membunuhmu Secara Langsung

Equal memberikan:

> **True Damage**

Tetapi yang jauh lebih penting adalah interaksinya dengan debuff.

Jika kamu masih memiliki:

### Magia Burn

Equal memberikan:

> **Shattered Will**

Efek:

**lethal DoT**

Artinya bisa membunuhmu.

---

### Stasis

Equal memberikan:

> **Shattered Soul**

Efek:

**lethal DoT**

---

### Sanctity

Jika kamu sudah terkena Sanctity lalu terkena Equal lagi:

> **Shattered Heart**

Efek:

**lethal DoT**

---

# 10. Jadi Apa Fungsi Equal?

Equal mempunyai dua fungsi besar.

## 1. Membersihkan debuff

Equal memberikan:

> **Sanctity**

Sanctity menghapus:

- Corruption
- Somber

Jadi Equal adalah mekanisme cleansing.

---

## 2. Menyembuhkan Malgor

Setiap Equal juga membantu memulihkan HP Malgor.

Inilah alasan:

```text
DPS besar
≠
fight otomatis mudah
```

Kalau party gagal mengontrol healing Malgor, fight dapat menjadi sangat panjang.

---

# 11. DECAY

Karena Equal menyembuhkan Malgor, **Decay** sangat berguna.

Contoh class:

- Legion Revenant
- class lain yang memiliki Decay sesuai setup

Timing Decay sangat penting.

Jangan asal menekan Decay setiap cooldown.

---

# 12. Timing Decay

Ketika Equal zone muncul:

```text
RED ZONE APPEARS
        ↓
siapkan Decay
        ↓
Equal
        ↓
Malgor mencoba heal
        ↓
Decay memotong healing
```

Untuk LR, guide komunitas merekomendasikan menekan **skill 2 / Decay** segera ketika Equal zone muncul.

Prinsip sederhananya:

> **Jangan sampai Decay cooldown lewat ketika Equal terjadi.**

---

# 13. Siklus Mekanik

Malgor menjalankan urutan yang sangat konsisten:

```text
TRUTH
  ↓
LISTEN
  ↓
EQUAL
  ↓
TRUTH
  ↓
LISTEN
  ↓
EQUAL
  ↓
repeat
```

AQW guide mencatat bahwa urutan voice line ini berulang sampai boss mati.

Ini sangat membantu karena kamu dapat memprediksi mekanik berikutnya.

---

# 14. Cara Membaca Fight

Jangan hanya melihat HP Malgor.

Dengarkan voice line.

### Jika terdengar:

> "I will make you see the truth."

Berarti:

```text
TRUTH
↓
taunt sesuai rotation
```

---

### Jika terdengar:

> "You shall listen."

Berarti:

```text
LISTEN
↓
taunt sesuai rotation
↓
siapkan movement
```

---

### Jika terdengar:

> "All stand equal beneath the eyes of the Eternal."

Berarti:

```text
EQUAL
↓
lihat red zone
↓
hanya player yang mendapat giliran masuk
↓
player lain keluar
```

---

# 15. ZONING

Istilah **zoning** berarti:

> pemain yang mendapat giliran harus berada di dalam red zone ketika Equal terjadi.

Setiap pemain biasanya mendapatkan giliran zoning **satu kali setiap loop**.

Contoh konsep:

```text
Loop:

SC → Zone
AP → Zone
LoO → Zone
LR → Zone

kemudian kembali ke:

SC → Zone
AP → Zone
LoO → Zone
LR → Zone
```

Urutan detail bergantung pada class composition/rotation yang digunakan.

---

# 16. Jika BUKAN Giliranmu

Ketika red zone muncul:

```text
BUKAN GILIRANMU
       ↓
JANGAN MASUK
       ↓
lari ke sisi arena
```

Ini penting.

Jangan berpikir:

> "Ah, satu orang sudah di dalam, gw ikut bantu."

Jangan.

Equal bukan mechanic yang harus ditank bersama.

---

# 17. Trick Movement Saat Terkena Listen

Masalah:

```text
Listen
 ↓
stun
 ↓
Equal muncul
 ↓
kamu tidak bisa bergerak
```

Solusi praktis yang digunakan pemain berpengalaman:

> **Input movement sebelum stun benar-benar mengenai karakter.**

Jadi jika kamu tahu Listen akan diikuti Equal dan kamu harus keluar:

```text
Listen mulai
     ↓
input movement lebih awal
     ↓
Stasis
     ↓
movement yang sudah diberikan membantu posisi
```

Jangan menunggu sampai karakter sudah petrified baru mencoba lari.

---

# 18. Taunt

Ultra Speaker membutuhkan koordinasi taunt.

**Scroll of Enrage (SoE)** dapat digunakan untuk class yang tidak mempunyai taunt bawaan.

Durasi taunt:

**sekitar 6 detik**

Penting:

> Taunt harus dilakukan ketika player berada dalam jangkauan Malgor.

Jangan berdiri terlalu jauh dari posisi boss lalu menekan Enrage.

---

# 19. Siapa yang Harus Taunt?

Tergantung composition.

Contoh setup standar:

```text
StoneCrusher
Lord of Order
ArchPaladin
Legion Revenant
```

Semua class mempunyai bagian rotation masing-masing.

AQWG juga mencatat alternatif seperti:

- Paladin Chronomancer
- Quantum Chronomancer
- Chaos Avenger

---

# 20. Standard 4-Class Setup

Setup yang sangat umum:

```text
┌──────────────────────────────┐
│ StoneCrusher                 │
│ Lord of Order               │
│ ArchPaladin                 │
│ Legion Revenant             │
└──────────────────────────────┘
```

Role:

### StoneCrusher

- Support
- Buff
- Taunt rotation
- Salah satu class paling mudah untuk belajar Speaker

### Lord of Order

- Support
- Buff
- Heal
- Taunt rotation

### ArchPaladin

- Defensive support
- Heal
- Damage reduction
- Taunt

### Legion Revenant

- Group DPS
- Support
- Decay
- Taunt
- Salah satu role yang lebih sulit karena timing Decay

---

# 21. Urutan Tingkat Kesulitan Class

Untuk belajar, salah satu guide Malgor merekomendasikan kira-kira:

```text
StoneCrusher
      ↓
Lord of Order
      ↓
ArchPaladin
      ↓
Legion Revenant
```

Bukan berarti class tersebut memiliki "kekuatan" berurutan.

Ini lebih ke:

> **seberapa banyak mekanik tambahan yang perlu diperhatikan pemain.**

StoneCrusher relatif sederhana.

LR lebih menuntut karena harus memperhatikan Decay dan timing taunt.

---

# 22. StoneCrusher

StoneCrusher termasuk class yang relatif mudah digunakan untuk Ultra Speaker.

Fokus:

```text
Support
+
Taunt
+
Zone
```

Tidak ada mekanik class yang terlalu rumit dibanding LR.

### Tips

Skill 5 StoneCrusher memiliki range yang pendek.

Jika kamu sedang keluar dari Equal zone:

> gunakan skill 5 sebelum meninggalkan area jika memungkinkan.

---

# 23. Lord of Order

Lord of Order relatif mudah.

Prinsip:

```text
Spam skill sesuai cooldown
+
ikuti taunt rotation
+
perhatikan zone
```

Salah satu masalahnya adalah Listen yang terjadi sebelum Equal.

Kalau kamu terkena stun dan kemudian Equal datang:

```text
Listen
↓
Stun
↓
Equal
↓
tidak bisa keluar
```

Karena itu:

> input movement lebih awal.

---

# 24. ArchPaladin

ArchPaladin mempunyai rotation taunt yang relatif mudah dalam setup standar.

Hal penting:

## Skill 4 → tunggu → Skill 5

Jangan sekadar:

```text
4 → 5 langsung
```

Guide Malgor merekomendasikan:

```text
Skill 4
   ↓
tunggu hampir habis
   ↓
Skill 5
```

Tujuannya agar:

- damage reduction tetap aktif lebih lama
- damage buff AP tetap dapat dipertahankan

Secara visual, cooldown 4 dan 5 dapat dibayangkan seperti dua jarum jam yang berada berlawanan.

---

# 25. Legion Revenant

LR lebih sulit.

Alasan utamanya:

## Decay

Equal menyembuhkan Malgor.

LR harus menggunakan Decay pada timing yang tepat.

Konsep:

```text
Equal zone muncul
       ↓
siapkan Decay
       ↓
Decay
       ↓
Malgor heal terkontrol
```

Jangan membuang Decay sembarangan sebelum Equal.

---

# 26. Equipment

Untuk first clear, survivability lebih penting daripada mengejar DPS maksimal.

Salah satu guide Malgor merekomendasikan:

### Weapon

**Valiance**

Karena memberikan utility untuk damage/survivability.

### Cape

**Penitence**

Bisa membantu survivability.

Alternatif yang relevan untuk beberapa support:

**Absolution**

---

# 27. Forge Helm

Untuk setup yang mengutamakan survivability:

> Hindari Forge helm yang mengurangi Endurance jika efek tersebut membuat HP terlalu rendah.

Guide Malgor secara khusus memperingatkan bahwa pengurangan Endurance dapat membuat player terkena one-shot.

---

# 28. Enhancement

Untuk first clear:

```text
Defense > Damage
```

Guide komunitas merekomendasikan Healer enhancement untuk class-class standar karena memberikan HP lebih besar.

Jika sudah sangat percaya diri dan tahu persis breakpoint survivability:

```text
Luck / Wizard
```

bisa dipertimbangkan.

Tetapi untuk belajar:

> jangan mengorbankan survivability hanya demi sedikit tambahan DPS.

---

# 29. Consumable

Consumable biasanya bukan syarat mutlak untuk clear normal.

Namun dapat membantu.

Contoh:

- Body Tonic
- Revitalize Elixir
- consumable defensive lainnya

Prinsip:

```text
First clear:
Defensive consumables

Speed clear:
Offensive consumables
```

Ada juga trick Revitalize:

> gunakan damage buffs terlebih dahulu sebelum meminum Elixir agar HoT yang dihasilkan lebih besar.

---

# 30. Damage Boost

Malgor tidak mempunyai tagged race.

Jadi racial boost seperti:

```text
+% damage to Human
+% damage to Dragon
```

tidak menjadi faktor.

Lebih berguna menggunakan:

```text
51% All Damage
```

jika tersedia.

Contoh:

**NSoD**

atau weapon All boost lain yang setara.

---

# 31. Boss Shield

The First Speaker memiliki Boss Shield.

Damage di atas:

**150,000**

mengalami diminishing return yang sangat ekstrem.

Artinya:

```text
1 hit = 100k
```

bukan berarti:

```text
1 hit = 100k
```

masih sepenuhnya efisien ketika damage mentah jauh melewati threshold.

Akibatnya:

> Jangan membangun seluruh strategi hanya untuk menghasilkan satu hit burst yang sangat besar.

Sustained damage dan mekanik yang benar jauh lebih penting.

---

# 32. Vindication

Ada mekanik penting:

> Jika Malgor membunuh seorang player, dia mendapatkan **+30% Defense**.

Disertai pesan:

> "We move closer to wiping the slate clean."

Jadi setiap kematian anggota party bukan hanya kehilangan satu pemain.

Kematian juga membuat boss lebih sulit dibunuh.

---

# 33. Apa yang Terjadi Kalau Mati?

Jika satu player mati:

Malgor mendapatkan:

```text
+30% Defense
```

Karena itu resurrection bukan sekadar:

> "tunggu respawn."

Party juga harus mempertimbangkan bahwa boss sekarang lebih tanky.

---

# 34. Kalau Mati di Awal Fight

Jika Malgor masih sekitar:

**>90% HP**

salah satu guide merekomendasikan:

> **Reset fight dan mulai ulang.**

Alasannya:

```text
Player mati
↓
Malgor +30% Defense
↓
fight makin sulit
↓
lebih banyak peluang error
```

Jika Malgor sudah jauh di bawah 90%:

> lebih masuk akal menggunakan waktu respawn untuk mempelajari posisi/rotation party dan melanjutkan.

---

# 35. Urutan Start vs Loop

Ini sangat penting.

Fight mempunyai bagian:

```text
START
```

yang hanya terjadi sekali.

Setelah itu:

```text
LOOP
```

berulang.

Urutan voice line secara umum:

```text
TRUTH
↓
LISTEN
↓
EQUAL
↓
TRUTH
↓
LISTEN
↓
EQUAL
↓
...
```

Namun **taunt dan zoning player tidak selalu sekadar bergantian berdasarkan voice line**.

Rotation tergantung composition.

Jadi jangan membuat aturan:

```text
"Setiap Truth = player A"
```

tanpa melihat chart composition yang dipakai party.

---

# 36. Chart Rotation

Untuk party standar, buat pembagian sebelum fight:

```text
Player 1 → Taunt A
Player 2 → Taunt B
Player 3 → Taunt C
Player 4 → Taunt D
```

Dan:

```text
Player 1 → Zone pada bagian tertentu
Player 2 → Zone berikutnya
Player 3 → Zone berikutnya
Player 4 → Zone berikutnya
```

Setiap pemain perlu mengetahui:

1. kapan taunt
2. kapan zone
3. kapan keluar zone
4. kapan menggunakan Decay
5. kapan menggunakan movement sebelum Listen

---

# 37. Contoh Mental Model Rotation

Jangan menghafal seperti:

```text
T1
T2
T3
T4
```

Lebih mudah:

```text
VOICE LINE
    ↓
mekanik apa?
    ↓
siapa yang bertugas?
    ↓
apa yang harus dilakukan?
```

Contoh:

```text
"I will make you see the truth."
          ↓
       TRUTH
          ↓
      TAUNT
```

Lalu:

```text
"You shall listen."
          ↓
       LISTEN
          ↓
      TAUNT
          ↓
prepare movement
```

Lalu:

```text
"All stand equal..."
          ↓
       EQUAL
          ↓
     RED ZONE
          ↓
 hanya 1 player
          ↓
   DECAY jika perlu
```

---

# 38. Kesalahan Paling Umum

## ❌ 1. Dua orang masuk Equal

Hasil:

```text
Equal
↓
damage meningkat
↓
party member bisa mati
```

### Solusi

```text
ONE PLAYER ONLY
```

---

## ❌ 2. Masuk Equal setelah terkena Truth

Jika masih terkena:

```text
Magia Burn
```

Equal dapat memberikan:

```text
Shattered Will
```

yang lethal.

### Solusi

Ikuti rotation dan jangan mengambil zone yang bukan milikmu.

---

## ❌ 3. Terkena Listen tepat sebelum Equal

```text
Listen
↓
Stasis
↓
Equal
↓
tidak bisa keluar
```

### Solusi

Input movement lebih awal ketika Listen akan datang.

---

## ❌ 4. Decay terlambat

```text
Equal
↓
Malgor heal
↓
Decay baru ditekan
```

Sudah terlambat.

### Solusi

Siapkan Decay sebelum Equal.

---

## ❌ 5. Taunt dari terlalu jauh

Scroll of Enrage harus digunakan dalam range yang efektif.

### Solusi

Tetap dekat dengan area Malgor saat waktunya taunt.

---

## ❌ 6. Semua orang bergerak ke red zone

Jangan.

Hanya player yang mendapat giliran.

---

## ❌ 7. Semua orang fokus DPS

Ultra Speaker bukan:

```text
4 DPS
→ spam skill
→ selesai
```

Mekanik adalah bagian utama fight.

---

## ❌ 8. Menggunakan setup glass cannon

First clear bukan waktu untuk:

```text
max DPS
minimum HP
```

Lebih baik:

```text
survive
→ execute mechanic
→ boss mati
```

---

# 39. Checklist Sebelum Pull

## Party

- [ ] 4 pemain
- [ ] Semua tahu role
- [ ] Semua tahu taunt rotation
- [ ] Semua tahu zoning rotation

## Equipment

- [ ] 51% All weapon jika tersedia
- [ ] Survivability cukup
- [ ] Cape defensif bila diperlukan
- [ ] Enhancement sesuai role

## Consumable

- [ ] Body Tonic
- [ ] Revitalize
- [ ] Scroll of Enrage jika dibutuhkan

## Knowledge

- [ ] Hafal Truth
- [ ] Hafal Listen
- [ ] Hafal Equal
- [ ] Tahu siapa yang zone
- [ ] Tahu kapan Decay
- [ ] Tahu kapan keluar zone

---

# 40. Callout Party yang Sederhana

Sebelum mulai:

```text
TRUTH = taunt sesuai rotation
LISTEN = taunt + prepare movement
EQUAL = one person only
LR = Decay Equal
```

Saat fight:

```text
TRUTH
↓
TAUNT

LISTEN
↓
TAUNT
↓
MOVE

EQUAL
↓
RED ZONE
↓
ONE PLAYER
↓
DECAY
```

---

# 41. Panduan untuk Pemain Baru

Kalau baru pertama kali, jangan langsung mencoba menguasai semua hal.

## Tahap 1 — Hafalkan 3 kata

```text
TRUTH
LISTEN
EQUAL
```

---

## Tahap 2 — Hafalkan arti

```text
TRUTH
→ TAUNT

LISTEN
→ TAUNT + PREPARE MOVEMENT

EQUAL
→ ONE PLAYER IN ZONE
```

---

## Tahap 3 — Hafalkan bahaya

```text
Truth + Equal
= DEADLY

Listen + Equal
= DEADLY

Multiple players in Equal
= VERY BAD
```

---

## Tahap 4 — Baru optimasi class

Setelah bisa survive:

```text
support rotation
↓
taunt timing
↓
zone timing
↓
Decay
↓
DPS optimization
```

---

# 42. Strategi Public Room

Jika masuk room random, sebelum fight tanyakan:

```text
"what comp?"
"who taunts?"
"who zones?"
"who decays?"
```

Jangan langsung attack.

Jika tidak ada yang tahu rotation:

> kemungkinan wipe sangat tinggi.

Ultra Speaker bukan boss yang ideal untuk:

```text
"gas aja bang"
```

---

# 43. Strategi Jika Party Wipe

Jangan langsung menyimpulkan:

> "DPS kurang."

Cari penyebab.

### Jika banyak orang mati saat Equal:

Kemungkinan:

```text
wrong zoning
atau
lebih dari satu player di zone
```

### Jika mati setelah Truth:

Kemungkinan:

```text
Magia Burn
```

### Jika mati karena tidak bisa bergerak:

Kemungkinan:

```text
Listen → Equal
```

### Jika boss heal terlalu banyak:

Kemungkinan:

```text
Decay timing salah
```

### Jika fight semakin lama setelah ada yang mati:

Kemungkinan:

```text
Vindication
+30% Defense per player killed
```

---

# 44. Flowchart Ultra Speaker

```text
                 START
                   │
                   ▼
             Malgor Attacks
                   │
                   ▼
                TRUTH
                   │
                   ├── TAUNT
                   │
                   ▼
               LISTEN
                   │
                   ├── TAUNT
                   │
                   ├── prepare movement
                   │
                   ▼
                EQUAL
                   │
             ┌─────┴─────┐
             │           │
        Your zone?    Not your zone
             │           │
            YES          NO
             │           │
             ▼           ▼
       Enter zone     Leave zone
             │           │
             └─────┬─────┘
                   │
                   ▼
             Equal resolves
                   │
                   ▼
            Cleanse / Heal
                   │
                   ▼
                 TRUTH
                   │
                   ▼
                 LOOP
```

---

# 45. Super Simple Version

Kalau semua teori terasa terlalu banyak, hafalkan ini:

```text
MALG0R:

TRUTH
→ TAUNT

LISTEN
→ TAUNT
→ SIAP-SIAP GERAK

EQUAL
→ RED ZONE
→ CUMA 1 ORANG

LR
→ DECAY SAAT EQUAL

JANGAN:
→ 2 ORANG DI ZONE
→ MASUK ZONE SAAT HABIS TRUTH/LISTEN
→ TELAT DECAY
→ TAUNT DARI JAUH
```

---

# 46. Referensi

## Sumber Resmi AQWorlds

**ShadowFlame Ultra Boss — March 24, 2023**

https://www.aq.com/gamedesignnotes/aqw-24mar23-malgorultraboss-9135

Dokumen resmi menjelaskan:

- Ultra Speaker / First Speaker
- reward
- autoattack debuff
- Equalizer
- healing boss
- kebutuhan taunt
- mekanik utama fight

---

## AQWorlds Wiki

**The First Speaker**

https://aqwwiki.wikidot.com/the-first-speaker

Digunakan untuk:

- HP
- attack
- cooldown
- Magia Burn
- Stasis
- Equalize
- Sanctity
- Shattered Will
- Shattered Soul
- Shattered Heart
- Boss Shield
- Vindication
- base stats

---

## AQWG

**Ultra Bosses**

https://sites.google.com/view/aqwg-net/ultra-bosses

Digunakan untuk:

- setup class
- Scroll of Enrage
- party composition
- Ultra Speaker rotation overview

---

## Ultra Malgor Guide

https://nandixer.github.io/malgor/

Digunakan untuk:

- konsep Truth / Listen / Equal
- zoning
- taunt
- class roles
- equipment
- potion
- recovery
- strategy chart

---

# 47. Catatan Patch / Perubahan Penting

AQWorlds pernah melakukan balance update terhadap The First Speaker setelah perilisan awal.

Perubahan yang tercatat secara resmi antara lain:

- healing Malgor dikurangi 25%
- defense buff Scintillation dikurangi dari 100% menjadi 75%
- Magia Burn magic vulnerability dinaikkan dari 100% menjadi 300%
- durasi Magia Burn dinaikkan dari 16 menjadi 18 detik
- Sanctity diubah sehingga Equal dapat membunuh player yang masih memiliki kondisi tersebut
- Malgor dikembalikan ke posisi saat Power Split

Karena AQWWiki terus diperbarui, angka mekanik sebaiknya selalu dibandingkan dengan wiki terbaru jika ada balance patch baru.

---

# 48. Final Cheat Sheet

```text
╔══════════════════════════════════════╗
║          ULTRA SPEAKER               ║
╠══════════════════════════════════════╣
║ TRUTH                                ║
║ → "I will make you see the truth."   ║
║ → TAUNT                              ║
║ → Magia Burn = +300% Magic Damage    ║
╠══════════════════════════════════════╣
║ LISTEN                               ║
║ → "You shall listen."                ║
║ → TAUNT                              ║
║ → STASIS / STUN                      ║
║ → PREPARE MOVEMENT                   ║
╠══════════════════════════════════════╣
║ EQUAL                                ║
║ → RED ZONE                           ║
║ → ONE PLAYER ONLY                    ║
║ → CLEANSES Corruption + Somber       ║
║ → HEALS MALGOR                       ║
║ → LR SHOULD DECAY                    ║
╠══════════════════════════════════════╣
║ DEATH                                ║
║ → Malgor +30% Defense                ║
╠══════════════════════════════════════╣
║ LOOP                                 ║
║ TRUTH → LISTEN → EQUAL → repeat      ║
╚══════════════════════════════════════╝
```

---

# 49. Inti Ultra Speaker

Ultra Speaker bukan terutama masalah:

> **"Punya DPS berapa?"**

Masalah utamanya adalah:

> **"Apakah empat pemain bisa menjalankan rotation tanpa salah?"**

Kalau seluruh party memahami:

```text
Truth
↓
Taunt

Listen
↓
Taunt
↓
Move

Equal
↓
One player zone
↓
Decay
↓
repeat
```

maka fight menjadi jauh lebih terstruktur.

**Rule nomor satu: jangan panik ketika red zone muncul.**

Lihat dulu:

```text
"Apakah ini giliran saya?"
```

Kalau bukan:

> **keluar.**

Kalau iya:

> **masuk sendirian.**

---

## Sumber yang dicek untuk panduan ini

- AQWorlds Design Notes — *ShadowFlame Ultra Boss* (2023)
- AQWorlds Wiki — *The First Speaker*
- AQWG — *Ultra Bosses*
- Ultra Malgor Guide — mekanik dan rotation
- Guide komunitas 2026 untuk tips Listen, Taunt, Decay, dan zoning

Panduan ini sengaja memisahkan **mekanik boss** dari **rotation class**, karena rotation taunt/zoning dapat berbeda berdasarkan komposisi party.
