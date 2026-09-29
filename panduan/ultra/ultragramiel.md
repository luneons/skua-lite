# Panduan Melawan Ultra Gramiel — AQW

> **Ultra Gramiel** adalah Ultra Boss Gramiel the Graceful di `/join ultragramiel`.
>
> Panduan ini dibuat setelah melakukan riset pada **AQWorlds Design Notes resmi, AQW Wiki, AQW Wiki mirror yang diperbarui, serta battle guide komunitas**. Fokus panduan ini adalah mekanik yang benar-benar menentukan clear: **Grace Crystal, taunt, Burning Ward, Crystal Explosion, Focus/Vendetta, Death's Door, breakpoint 70/40/10%, dan Grace Shield**.
>
> **Catatan patch:** mekanik boss dapat berubah jika AQWorlds melakukan balance update. Panduan ini mengikuti data yang tersedia pada saat penyusunan, September 2026.

---

# 1. Informasi Dasar

## Lokasi

```text
/join ultragramiel
```

## Syarat

- Level **80+**
- Room maksimal **4 pemain**
- Map merupakan locked zone.
- Boss terdiri dari:
  - **2x Grace Crystal**
  - **Gramiel the Graceful**

AQW Wiki mencatat bahwa Grace Crystal memiliki level 95 dan Gramiel juga level 95. Gramiel memiliki **7,500,000 HP**. citeturn1search0turn1search1turn1search3

---

# 2. Gambaran Besar Fight

Ultra Gramiel mempunyai **2 fase utama**:

```text
PHASE 1
2x Grace Crystal
        ↓
bunuh Crystal
        ↓
PHASE 2
Gramiel the Graceful
        ↓
70%
        ↓
40%
        ↓
10%
        ↓
KILL
```

**Jangan langsung menyerang Gramiel.**

AQWorlds sendiri menjelaskan mekaniknya secara sederhana:

> Gramiel tidak akan turun sampai crystal-nya dihancurkan.

Dan karena Gramiel serta crystal memiliki mekanik reflect, penggunaan class AoE harus diperhatikan. citeturn0search0

---

# 3. Hal yang Paling Penting

Kalau kamu baru belajar, cukup hafalkan lima hal ini:

```text
1. CRYSTAL DULU
2. SEMUA PLAYER PERLU TAUNT
3. JANGAN ASAL AOE
4. JANGAN BIARKAN CRYSTAL TERAKHIR HIDUP SETELAH SATUNYA MATI
5. PHASE 2 PUNYA FOCUS → VENDETTA → DEATH'S DOOR
```

---

# 4. PHASE 1 — Grace Crystal

Ada **dua Grace Crystal**.

Keduanya mempunyai:

- 400 HP
- Level 95
- Boss Shield
- Burning Ward
- Tidak bisa di-stun

Yang paling penting:

> **Setiap serangan yang mengenai Grace Crystal memantulkan damage balik kepada attacker.**

AQW Wiki mencatat Burning Ward pada Crystal memantulkan **150 damage per instance damage** yang diberikan pemain. citeturn1search1

---

# 5. Crystal Mempunyai Boss Shield Ekstrem

Grace Crystal mempunyai Boss Shield yang membuat:

> **Satu serangan tidak dapat memberikan lebih dari 1 damage.**

Artinya:

```text
Hit kecil       → 1 damage
Hit besar       → 1 damage
Burst besar     → 1 damage
AoE             → masing-masing hit tetap terkena mekanik
```

Karena itu, jangan berpikir:

> "Pakai class burst paling sakit supaya Crystal cepat mati."

Mekaniknya memang sengaja membatasi damage per hit. citeturn1search1

---

# 6. Burning Ward

Setiap kali kamu memberikan damage kepada Crystal:

```text
Kamu hit Crystal
      ↓
Crystal reflect
      ↓
Kamu menerima 150 damage
```

Jadi class dengan banyak hit/AoE dapat menerima reflect berkali-kali.

Contoh konsep:

```text
1 hit
→ 150 reflect

10 hits
→ sekitar 1500 reflect
```

Angka aktual dapat dipengaruhi kondisi combat, tetapi prinsipnya:

> **Semakin banyak instance damage, semakin banyak peluang terkena reflect.**

---

# 7. Kenapa AoE Berbahaya?

Bayangkan dua Crystal masih hidup:

```text
Crystal A
Crystal B
```

Kalau kamu memakai skill multi-target yang mengenai keduanya:

```text
Skill
 ├── Hit Crystal A
 │      ↓
 │   reflect
 │
 └── Hit Crystal B
        ↓
     reflect
```

Akibatnya HP player dapat turun sangat cepat.

AQWorlds secara resmi memperingatkan bahwa Gramiel dan crystal-nya merefleksikan damage sehingga class multi-target/AoE perlu digunakan dengan hati-hati. citeturn0search0

---

# 8. Fokus Crystal yang Benar

Kamu harus membunuh **kedua Crystal**.

Namun ada mekanik penting:

> Jika satu Crystal mati, Crystal yang tersisa menjadi **Unstable**.

Urutannya:

```text
Crystal A ─── hidup
Crystal B ─── hidup

        ↓

Crystal A mati

        ↓

Crystal B = UNSTABLE

        ↓
Crystal B mulai charge

        ↓
CRYSTAL EXPLOSION

        ↓
INSTANT DEATH
```

---

# 9. Crystal Explosion

Saat hanya satu Crystal tersisa, Crystal tersebut menggunakan:

**Unstable → Crystal Explosion**

Unstable melakukan charge sekitar **5 detik**.

Setelah charge selesai:

> **Crystal Explosion = Instant Death**

Dan damage tersebut:

- True Damage
- Instant Death
- Mengabaikan Focus

AQW Wiki mencatat bahwa Crystal Explosion digunakan setelah charge 5 detik dan akan membunuh secara instan. citeturn1search1

---

# 10. Cara Mengatasi Unstable

Begitu Crystal pertama mati:

```text
STOP DPS LAIN
       ↓
SEMUA FOKUS CRYSTAL TERAKHIR
       ↓
BUNUH SEBELUM CHARGE SELESAI
```

Ini salah satu bagian paling penting di seluruh fight.

Jangan:

```text
Crystal A mati
↓
"nice"
↓
balik DPS Gramiel
```

Itu salah.

Ketika satu Crystal mati:

> **Crystal yang tersisa menjadi prioritas absolut.**

---

# 11. Jangan Membunuh Dua Crystal Secara Bersamaan dengan Asal AoE

Idealnya party tahu target yang sedang dipukul.

Contoh:

```text
Semua DPS
    ↓
Crystal A
    ↓
Crystal A mati
    ↓
SEMUA
    ↓
Crystal B
    ↓
Crystal B mati
    ↓
PHASE 2
```

Jangan membuat situation:

```text
A = hampir mati
B = hampir mati
AoE besar
↓
A mati
↓
B tidak mati
↓
Unstable
↓
party panik
```

---

# 12. Taunt di Phase 1

Battle guide komunitas untuk Ultra Gramiel mencatat bahwa **keempat player perlu memiliki Scroll of Enrage dan melakukan taunt**, dengan **taunt cycle berbeda antara fase Crystal dan fase Gramiel**. citeturn1youtube12

Jadi jangan masuk room dengan asumsi:

> "Cukup satu tank."

Untuk setup standar, koordinasikan empat player sebelum pull.

---

# 13. Scroll of Enrage

**Scroll of Enrage (SoE)** digunakan untuk taunt.

Tujuan taunt:

```text
Boss attack
    ↓
target diarahkan sesuai rotation
    ↓
damage/debuff tidak acak
```

Dalam Ultra Gramiel, taunt bukan sekadar:

```text
spam Enrage
```

Tetapi harus mengikuti rotation.

---

# 14. Jangan Mengarang Rotation Sendiri

Ultra Gramiel mempunyai:

```text
PHASE 1 TAUNT ROTATION
```

dan

```text
PHASE 2 TAUNT ROTATION
```

yang berbeda.

Karena itu, sebelum pull:

```text
Player 1 = Taunt A
Player 2 = Taunt B
Player 3 = Taunt C
Player 4 = Taunt D
```

Sepakati siapa melakukan taunt pada urutan masing-masing.

Battle guide komunitas secara eksplisit mendokumentasikan dua taunt cycle berbeda untuk kedua fase. citeturn1youtube12

---

# 15. PHASE 2 — Gramiel

Setelah kedua Crystal mati:

```text
Crystal A
   ↓
mati

Crystal B
   ↓
mati

        ↓

Gramiel Phase 2
```

Gramiel menggunakan:

**Grace Charge**

Pada awal Phase 2, Gramiel mendapatkan:

- **+5000% Crit Chance**
- **+500% Outgoing Damage**
- DamageShield
- Boss Shield Phase 1 dihapus
- stack Boon/Absorbed di-reset

AQW Wiki mencatat efek tersebut pada awal Phase 2. citeturn2search0

Jadi:

> Phase 2 bukan berarti boss menjadi santai.

Justru serangan Gramiel menjadi sangat berbahaya.

---

# 16. Phase 2 Boss Shield

Setelah Phase 2 dimulai, Gramiel menggunakan DamageShield.

Damage di atas:

**125,000**

dikurangi menggunakan exponent **0.8**, dengan damage efektif tidak turun di bawah 125,000.

Artinya burst sangat besar tidak selalu menghasilkan damage sebesar angka mentahnya. citeturn2search0

Secara sederhana:

```text
≤ 125k
→ normal

> 125k
→ excess damage terkena diminishing return
```

Jadi sustained DPS tetap penting.

---

# 17. Glory / Boon of Grace

Serangan normal Gramiel dapat memberikan:

**Boon of Grace**

Efek:

> Outgoing Damage Gramiel +2% selama 12 detik.

Stack berdasarkan player yang terkena.

Jadi semakin banyak player yang terkena serangan yang memberikan stack:

```text
Gramiel
+2%
+2%
+2%
...
```

semakin sakit.

AQW Wiki mencatat efek stack tersebut. citeturn2search0

---

# 18. Jangan Sembarangan Menggunakan Decay

Ini salah satu jebakan penting.

Jika **Decay aktif pada Gramiel**, serangan tertentu Gramiel dapat:

```text
menghapus Decay
+
memberikan Grace Ward
+
meningkatkan Outgoing Physical/Magic Damage
```

Grace Ward meningkatkan outgoing damage Gramiel sebesar **25% selama 30 detik**, dan efeknya dapat stack. citeturn2search0

Jadi:

> **Decay bukan sesuatu yang otomatis boleh dispam pada Gramiel.**

Kalau party menggunakan Decay, harus tahu kapan window yang aman.

---

# 19. Grace Shield

Setelah **3 kali Scorching Light**, Gramiel menggunakan:

**Grace Shield → Grace Drain**

Grace Shield:

- charge selama sekitar 5 detik
- memberikan Safeguard
- memblokir damage
- menonaktifkan Burning Ward selama aktif

Setelah charge:

**Grace Drain**

Jika Safeguard aktif:

- player mendapat **Grace Drained**
- Haste turun **70%**
- Hit Chance turun **70%**
- Gramiel mendapat **Grace Absorbed**
- Outgoing Damage Gramiel naik **30% per player yang terkena**
- stack selama 30 detik

AQW Wiki mencatat seluruh rangkaian ini. citeturn2search0

---

# 20. Apa yang Harus Dilakukan Saat Grace Shield?

Ketika Gramiel mengatakan:

> **"Gramiel attempts to drain your power… break his guard!"**

akan muncul window charge.

Tujuan:

```text
Grace Shield
      ↓
BURST / BREAK SHIELD
      ↓
jangan biarkan Gramiel mendapatkan banyak player
      ↓
lanjut fight
```

Jika Grace Drain berhasil mengenai banyak player:

```text
lebih banyak player terkena
       ↓
lebih banyak Grace Absorbed
       ↓
Gramiel semakin sakit
```

Jadi:

> Jangan santai ketika Grace Shield muncul.

---

# 21. Celestial Ruin

Ini adalah mekanik penting Phase 2.

Gramiel menggunakan:

**Celestial Ruin**

Efek:

> Mengurangi Damage Resistance dan Physical Resistance sebesar **40% selama 45 detik**.

Stack.

Jadi player yang terkena berulang kali menjadi semakin rentan. citeturn2search0

---

# 22. Focus

Focus adalah bagian yang sangat penting dalam strategi Phase 2.

Jika player menggunakan **Focus** pada Gramiel ketika Celestial Ruin aktif:

```text
Focus
  ↓
Gramiel merespons
  ↓
Vendetta diberikan kepada player
```

Vendetta:

- durasi 45 detik
- dapat stack sampai **5**

AQW Wiki mencatat bahwa Celestial Ruin + Focus menghasilkan Vendetta pada player yang menggunakan Focus. citeturn2search0

---

# 23. Vendetta

Ini adalah mekanik yang harus dipantau.

```text
Vendetta 1
Vendetta 2
Vendetta 3
Vendetta 4
Vendetta 5
```

Jangan sampai kamu mencapai:

```text
5 Vendetta
```

dan kemudian terkena mekanik berikutnya.

---

# 24. Death's Door

Gramiel menggunakan:

**Empowered Scorching Light**

Damage:

> **80% current HP**

Player yang mempunyai Vendetta akan mendapatkan:

> **Death's Door**

Death's Door berlangsung sekitar 60 detik.

Jadi:

```text
Focus
 ↓
Vendetta
 ↓
Empowered Scorching Light
 ↓
Death's Door
```

Ini bukan combo yang ingin kamu biarkan menumpuk sembarangan. citeturn2search0

---

# 25. Magic Amp / Unleashed Grace

Setelah **3 kali Empowered Scorching Light**, Gramiel melakukan:

**Channeling Grace**

Charge sekitar 5 detik.

Kemudian:

**Unleashed Grace**

Efek paling penting:

> Player dengan **5 stack Vendetta** akan terkena **Instant Death**.

Selain itu:

- Celestial Reckoning diberikan kepada player yang masih mempunyai Celestial Ruin/Vendetta
- Magic Resistance turun 25%
- Celestial Ruin dan Vendetta dihapus

AQW Wiki mencatat mekanik tersebut. citeturn2search0

---

# 26. Rule Besar Vendetta

Ingat:

```text
Vendetta 1
   ↓
Vendetta 2
   ↓
Vendetta 3
   ↓
Vendetta 4
   ↓
Vendetta 5
   ↓
UNLEASHED GRACE
   ↓
INSTANT DEATH
```

Jadi jangan asal menggunakan Focus.

---

# 27. Breakpoint 70% / 40% / 10%

Ini adalah salah satu mekanik paling penting.

Gramiel menggunakan:

**Celestial Rapture → Vanquish**

pada:

```text
70% HP
40% HP
10% HP
```

Saat breakpoint tercapai:

```text
Gramiel
↓
Invulnerable
↓
5 detik
↓
player tertentu juga menjadi Invulnerable
↓
Vendetta / Death's Door dihapus
↓
Vanquish
↓
Instant Death
```

AQW Wiki mencatat bahwa Invulnerable digunakan pada 70%, 40%, dan 10% HP, dan Vanquish terjadi setelah charge. citeturn2search0

---

# 28. Kenapa Breakpoint Ini Penting?

Karena player yang sedang mempunyai:

```text
Vendetta
atau
Death's Door
```

juga mendapatkan Invulnerable dan efek tersebut kemudian dihapus.

Jadi breakpoint berfungsi sebagai semacam:

```text
mechanic reset
```

Tetapi:

> Jangan menganggap breakpoint sebagai alasan untuk bermain sembarangan.

Vanquish tetap merupakan instant-death mechanic.

---

# 29. Jangan Panik Saat Gramiel Menjadi Invulnerable

Jika Gramiel mencapai:

```text
70%
40%
10%
```

dan tiba-tiba damage tidak masuk:

> **Jangan spam skill.**

Tunggu mechanic selesai.

Urutannya:

```text
Breakpoint
↓
Invulnerable
↓
charge
↓
Vanquish
↓
mechanic selesai
↓
damage lagi
```

---

# 30. Player Death = Sangat Mahal

Jika Gramiel membunuh seorang player:

1. Gramiel memulihkan **750,000 HP**
2. Gramiel mendapatkan **+20% Outgoing Damage**
3. Gramiel mendapatkan **+20% Outgoing Physical Damage**

Efek ini disebut:

**Grace Claimed**

dan disertai pesan:

> "In the end, you were nothing but a monster."

AQW Wiki mencatat efek ini secara eksplisit. citeturn2search0

Jadi:

```text
1 player mati
↓
Gramiel heal 750k
↓
Gramiel +20% damage
```

Death sangat mahal.

---

# 31. Jangan Berpikir "Nanti di-Revive"

Kalau ada player mati:

```text
Player mati
↓
Gramiel heal
↓
Gramiel damage naik
↓
party semakin sulit
```

Karena itu prioritas utama:

> **Survive > greed DPS.**

---

# 32. Recommended Mindset

Jangan bermain seperti:

```text
"Seberapa cepat kita bisa membunuh Gramiel?"
```

Gunakan mindset:

```text
"Bagaimana kita memastikan tidak ada mechanic yang gagal?"
```

Karena satu kematian dapat memberikan:

```text
+750k HP
+
+20% outgoing
+
+20% physical
```

kepada Gramiel. citeturn2search0

---

# 33. Party Composition

Karena room hanya 4 pemain, pembagian role harus jelas.

Setup yang umum digunakan oleh community guide adalah:

```text
Support
Support
DPS
DPS / Utility
```

Class yang dapat muncul dalam berbagai setup Ultra antara lain:

- Lord of Order
- Legion Revenant
- ArchPaladin
- StoneCrusher
- Chaos Avenger
- class DPS endgame lainnya

Namun untuk Ultra Gramiel, **class bukan satu-satunya masalah**.

Battle guide komunitas menekankan bahwa keempat player perlu menyiapkan taunt dan memahami taunt cycle. citeturn1youtube12

---

# 34. Mengapa 4 Player Perlu Siap Taunt?

Karena taunt rotation berubah antar fase.

```text
PHASE 1
Crystal
↓
Taunt Cycle A

PHASE 2
Gramiel
↓
Taunt Cycle B
```

Jadi:

> Jangan hanya satu orang yang membawa Scroll of Enrage.

Lebih aman:

```text
Player 1 → SoE
Player 2 → SoE
Player 3 → SoE
Player 4 → SoE
```

sesuai guide/community rotation yang digunakan party. citeturn1youtube12

---

# 35. Scroll of Enrage

Untuk pemain yang tidak memiliki taunt bawaan:

**Scroll of Enrage**

adalah solusi standar.

Sebelum masuk:

```text
check inventory
↓
Scroll of Enrage ada?
↓
YES
↓
siap
```

Jangan baru mencari Scroll of Enrage setelah party sudah pull.

---

# 36. AoE Class

AQWorlds resmi memberikan peringatan khusus:

> Gramiel dan crystal merefleksikan damage.

Jadi class dengan AoE / multi-target harus digunakan dengan hati-hati. citeturn0search0

Contoh mental model:

```text
AoE besar
↓
banyak hit
↓
Crystal reflect
↓
HP kamu turun
```

Kalau belum hafal phase 1:

> jangan asal spam AoE.

---

# 37. Legion Revenant

LR bisa sangat berguna karena:

- group support
- AoE
- DPS
- utility

Tetapi:

> AoE pada Crystal harus diperhatikan.

Selain itu, **Decay** juga perlu digunakan dengan timing yang tepat pada Gramiel karena Gramiel dapat menghapus Decay dan mendapatkan Grace Ward. citeturn2search0

Jadi LR bukan sekadar:

```text
spam semua skill
```

---

# 38. ArchPaladin

AP dapat digunakan sebagai:

- defensive support
- healing
- damage reduction
- taunt/utility

Untuk Ultra Gramiel, kemampuan bertahan hidup sangat berharga karena:

```text
death
↓
Gramiel +750k HP
↓
+20% damage
```

citeturn2search0

---

# 39. Lord of Order

LoO berfungsi terutama sebagai support:

- buff
- debuff
- heal
- party utility

Jangan mengejar DPS pribadi jika itu membuat buff/debuff utama party berantakan.

---

# 40. StoneCrusher

StoneCrusher dapat digunakan sebagai support dan membantu taunt rotation.

Karena Ultra Gramiel sangat bergantung pada koordinasi:

```text
SC
+
LoO
+
AP
+
DPS
```

adalah contoh party yang masuk akal untuk pembelajaran, dengan catatan rotation taunt tetap harus disepakati sebelum fight.

---

# 41. Equipment

Untuk first clear:

```text
SURVIVABILITY
>
PURE DPS
```

Pastikan:

- HP cukup
- damage resistance memadai
- weapon damage boost endgame jika tersedia
- enhancement sesuai class

Jangan mengorbankan survival hanya untuk beberapa persen DPS.

---

# 42. Damage Boost

Gramiel tidak perlu diperlakukan seperti boss race-tag tertentu hanya karena lore-nya.

Prioritas umum:

```text
All Damage
```

lebih universal.

Jika memiliki weapon endgame dengan:

```text
51% All Damage
```

itu dapat menjadi pilihan umum.

Namun gear tidak akan menyelamatkan party yang gagal menjalankan mechanic.

---

# 43. Boss Shield dan Burst

Phase 1:

```text
Crystal
→ max 1 damage per attack
```

Phase 2:

```text
≤125k
→ normal

>125k
→ diminishing return
```

Jadi jangan mengandalkan satu serangan absurd besar.

Sustained damage lebih masuk akal.

---

# 44. Strategi Phase 1 Lengkap

## Step 1

Masuk:

```text
/join ultragramiel
```

---

## Step 2

Pastikan:

```text
4 player
+
taunt ready
+
semua tahu target
```

---

## Step 3

Pilih:

```text
Crystal A
```

---

## Step 4

Semua DPS fokus Crystal A.

Hindari:

```text
unnecessary AoE
```

---

## Step 5

Ketika Crystal A mati:

```text
CRYSTAL B = UNSTABLE
```

---

## Step 6

Semua langsung pindah:

```text
Crystal B
```

---

## Step 7

Bunuh Crystal B sebelum:

```text
Unstable
↓
5 sec charge
↓
Crystal Explosion
```

---

## Step 8

Kedua Crystal mati:

```text
PHASE 2
```

---

# 45. Strategi Phase 2 Lengkap

Setelah Crystal kedua mati:

```text
Gramiel Grace Charge
```

Party:

```text
stay focused
↓
ikuti taunt rotation Phase 2
↓
jangan asal Focus
↓
pantau Vendetta
↓
pantau Death's Door
```

---

# 46. Focus Rule

Kalau party memakai strategi Focus:

```text
Focus
↓
Celestial Ruin
↓
Vendetta
```

Jangan sampai:

```text
Vendetta ×5
↓
Unleashed Grace
↓
DEAD
```

---

# 47. Death's Door Rule

Jika kamu terkena:

```text
Death's Door
```

jangan menganggap:

> "HP masih ada."

Karena mechanic berikutnya dapat menjadi lethal.

Pantau:

```text
Death's Door
+
Vendetta
```

dan ikuti rotation yang sudah ditentukan party.

---

# 48. Grace Shield Rule

Ketika Grace Shield muncul:

```text
BREAK SHIELD
```

Karena jika Grace Drain berhasil mengenai banyak player:

```text
Haste -70%
Hit Chance -70%
Gramiel +30% damage per player
```

citeturn2search0

---

# 49. Breakpoint Rule

Saat HP mendekati:

```text
70%
40%
10%
```

bersiap.

```text
STOP PANIC DPS
        ↓
INVULNERABLE
        ↓
WAIT
        ↓
VANQUISH
        ↓
CONTINUE
```

Jangan mengira boss bug ketika damage tiba-tiba tidak masuk.

---

# 50. Apa yang Harus Dilakukan Jika Ada yang Mati?

## Jika Crystal Phase

Karena Crystal Explosion sangat berbahaya:

```text
jika party kacau
↓
jangan memaksa
↓
reset lebih baik
```

## Jika Gramiel Phase

Ingat:

```text
player death
↓
Gramiel +750k HP
↓
+20% outgoing
↓
+20% physical
```

citeturn2search0

Jika masih awal fight, restart sering lebih masuk akal daripada mencoba membawa fight yang sudah diperberat.

---

# 51. Kesalahan Paling Umum

## ❌ 1. Langsung menyerang Gramiel

Salah.

```text
Crystal dulu.
```

AQWorlds resmi menyatakan Gramiel tidak akan turun sebelum crystal-nya dikalahkan. citeturn0search0

---

## ❌ 2. Menggunakan AoE sembarangan

Crystal reflect damage.

---

## ❌ 3. Crystal pertama mati, lalu balik ke Gramiel

Salah.

Crystal kedua:

```text
UNSTABLE
```

dan akan melakukan instant-death explosion.

---

## ❌ 4. Semua player tidak membawa taunt

Battle guide komunitas menyarankan keempat player siap taunt/Scroll of Enrage. citeturn1youtube12

---

## ❌ 5. Spam Decay

Gramiel dapat menghapus Decay dan mendapatkan Grace Ward.

---

## ❌ 6. Spam Focus

Focus berhubungan dengan:

```text
Celestial Ruin
↓
Vendetta
↓
Death's Door
↓
5 Vendetta
↓
Instant Death
```

---

## ❌ 7. Tidak memperhatikan 70/40/10%

Ini breakpoint penting.

---

## ❌ 8. Menganggap mati bisa di-revive gratis

Tidak.

Gramiel mendapatkan:

```text
750,000 HP
+
20% Outgoing
+
20% Physical
```

setiap kali membunuh player. citeturn2search0

---

# 52. Checklist Sebelum Pull

## Party

- [ ] 4 player
- [ ] Semua tahu role
- [ ] Semua membawa Scroll of Enrage jika dibutuhkan
- [ ] Taunt rotation sudah disepakati
- [ ] Crystal target sudah ditentukan

## Phase 1

- [ ] Crystal A dulu
- [ ] Hindari AoE berlebihan
- [ ] Perhatikan reflect
- [ ] Crystal pertama mati
- [ ] Langsung Crystal kedua
- [ ] Bunuh sebelum Crystal Explosion

## Phase 2

- [ ] Jangan asal Focus
- [ ] Pantau Vendetta
- [ ] Pantau Death's Door
- [ ] Break Grace Shield
- [ ] Jangan asal Decay
- [ ] Siap pada 70%
- [ ] Siap pada 40%
- [ ] Siap pada 10%

---

# 53. Cheat Sheet Phase 1

```text
┌───────────────────────────────────┐
│          PHASE 1                  │
├───────────────────────────────────┤
│ Crystal A + Crystal B             │
│                                   │
│ → pilih SATU Crystal              │
│ → DPS fokus                       │
│ → hati-hati AoE                   │
│ → Burning Ward = reflect          │
│                                   │
│ Crystal A mati                    │
│        ↓                          │
│ Crystal B = UNSTABLE              │
│        ↓                          │
│ 5 detik charge                    │
│        ↓                          │
│ CRYSTAL EXPLOSION = INSTANT DEATH │
│        ↓                          │
│ bunuh Crystal B                   │
│        ↓                          │
│ PHASE 2                            │
└───────────────────────────────────┘
```

---

# 54. Cheat Sheet Phase 2

```text
┌───────────────────────────────────┐
│          PHASE 2                  │
├───────────────────────────────────┤
│ Grace Charge                      │
│        ↓                          │
│ Taunt rotation                    │
│        ↓                          │
│ Celestial Ruin                    │
│        ↓                          │
│ Focus → Vendetta                  │
│        ↓                          │
│ Death's Door                      │
│        ↓                          │
│ 5 Vendetta = DEAD                 │
│                                   │
│ 70% → Invulnerable → Vanquish     │
│ 40% → Invulnerable → Vanquish     │
│ 10% → Invulnerable → Vanquish     │
└───────────────────────────────────┘
```

---

# 55. Mental Model Paling Sederhana

Kalau kamu baru belajar Ultra Gramiel, ingat:

```text
CRYSTAL
↓
SINGLE TARGET
↓
REFLECT
↓
FIRST CRYSTAL DEAD
↓
KILL SECOND CRYSTAL FAST
↓
GRAMIEL
↓
TAUNT
↓
FOCUS / VENDETTA MECHANIC
↓
70 / 40 / 10
↓
KILL
```

---

# 56. Versi Super Singkat untuk Discord/Party

```text
ULTRA GRAMIEL:

PHASE 1:
Crystal dulu.
Jangan spam AoE karena reflect.
Kill Crystal 1.
Crystal 2 langsung jadi UNSTABLE.
SEMUA DPS Crystal 2 sampai mati sebelum explosion.

PHASE 2:
Ikuti taunt rotation.
Jangan asal Focus.
Pantau Vendetta + Death's Door.
Break Grace Shield.
Jangan asal Decay.

70 / 40 / 10:
Boss invul.
Tunggu mechanic selesai.
Jangan panik.

Kalau mati:
Gramiel heal 750k + damage naik.
Jadi jangan greed.
```

---

# 57. Catatan Penting tentang Data

Ada perbedaan penamaan/tooltip antara beberapa database AQW.

Contohnya, beberapa sumber menyebut serangan awal sebagai:

- **Boon of Grace / Scorching Light**

sementara mirror/database lain menggunakan:

- **Glory of Grace / Grace Burst**

Perbedaan nama tersebut tidak mengubah mekanik inti yang perlu dipahami:

```text
damage scaling
+
Grace Shield
+
Grace Drain
+
Phase 2
+
Celestial Ruin
+
Vendetta
+
Death's Door
+
breakpoint 70/40/10
```

Untuk panduan ini, angka mekanik diprioritaskan dari AQW Wiki yang diperbarui dan dicocokkan dengan sumber resmi AQWorlds.

---

# 58. Sumber Riset

## AQWorlds — Official Design Notes

**Hollowborn Vindicator Class & Ultra Boss**

https://www.aq.com/gamedesignnotes/aqw-update-20june25-10026

Sumber resmi untuk:
- pengumuman Ultra Gramiel
- `/ultragramiel`
- syarat level 80
- mekanik Crystal
- peringatan reflect
- reward

citeturn0search0

---

## AQWorlds — Official Design Notes

**HollowBorn Class & Ultra Boss**

https://www.aq.com/gamedesignnotes/aqw-update-27june25-hbultraboss-10030

Sumber resmi untuk:
- rilis Ultra Gramiel
- Hollowborn Vindicator
- reward
- Ultra Gramiel Hub

citeturn0search1

---

## AQW Wiki — Ultra Gramiel

https://aqwwiki.wikidot.com/ultra-gramiel

Digunakan untuk:
- lokasi
- room limit
- Grace Crystal
- Gramiel
- level
- akses

citeturn1search0

---

## AQW Wiki — Grace Crystal

https://aqwwiki.wikidot.com/grace-crystal

Digunakan untuk:
- 400 HP
- Crystal Charge
- Crystal Pulse
- Grace Shattered
- Unstable
- Crystal Explosion
- Burning Ward
- Boss Shield
- 5-second charge
- instant death

citeturn1search1

---

## AQW Wiki — Gramiel the Graceful

https://aqwwiki.wikidot.com/gramiel-the-graceful

Digunakan untuk:
- HP
- Boon/Glory of Grace
- Scorching Light
- Grace Shield
- Grace Drain
- Grace Charge
- Celestial Ruin
- Vendetta
- Death's Door
- Magic Amp
- Unleashed Grace
- 70/40/10 breakpoint
- Vanquish
- Grace Claimed
- Boss Shield

citeturn1search3turn2search0

---

## AQW Wiki Mirror — Gramiel

https://aqw.alfian.web.id/gramiel-the-graceful

Digunakan sebagai cross-check untuk data mekanik Gramiel dan efek Phase 2.

citeturn1search2

---

## Community Battle Guide

**MrGoon — AQW Ultra Gramiel Battle Guide**

https://www.youtube.com/watch?v=7muM4I8LSWs

Digunakan untuk cross-check:
- 2-phase strategy
- kebutuhan taunt/Scroll of Enrage
- perbedaan taunt cycle Phase 1 dan Phase 2
- penggunaan class/AoE

citeturn1youtube12

---

# 59. FINAL CHEAT SHEET

```text
╔════════════════════════════════════════╗
║          ULTRA GRAMIEL                 ║
╠════════════════════════════════════════╣
║ PHASE 1                                ║
║                                        ║
║ 2x GRACE CRYSTAL                       ║
║                                        ║
║ • Crystal = 1 damage / hit             ║
║ • Damage reflect                       ║
║ • Hindari AoE sembarangan              ║
║ • Bunuh Crystal 1                      ║
║ • Crystal 2 → UNSTABLE                 ║
║ • 5 sec → INSTANT DEATH                ║
║ • Bunuh Crystal 2 secepat mungkin      ║
╠════════════════════════════════════════╣
║ PHASE 2                                ║
║                                        ║
║ GRAMIEL                                ║
║                                        ║
║ • Taunt rotation                       ║
║ • Celestial Ruin                       ║
║ • Focus → Vendetta                     ║
║ • Death's Door                         ║
║ • 5 Vendetta → instant death           ║
║ • Grace Shield → break                 ║
║ • Jangan asal Decay                    ║
╠════════════════════════════════════════╣
║ BREAKPOINTS                            ║
║                                        ║
║ 70% → Invulnerable → Vanquish          ║
║ 40% → Invulnerable → Vanquish          ║
║ 10% → Invulnerable → Vanquish          ║
╠════════════════════════════════════════╣
║ KALAU PLAYER MATI                      ║
║                                        ║
║ Gramiel: +750,000 HP                   ║
║ +20% Outgoing Damage                   ║
║ +20% Outgoing Physical Damage          ║
╚════════════════════════════════════════╝
```

---

# 60. Inti Ultra Gramiel

Ultra Gramiel bukan boss yang dimenangkan hanya dengan DPS.

Kunci sebenarnya:

```text
MECHANIC
   +
TAUNT
   +
CRYSTAL CONTROL
   +
VENDETTA CONTROL
   +
BREAKPOINT AWARENESS
   =
CLEAR
```

Kalau ingin mengingat hanya **3 aturan**:

### 1. Crystal dulu

```text
Crystal → Crystal → Gramiel
```

### 2. Jangan biarkan Crystal terakhir melakukan Explosion

```text
Crystal pertama mati
↓
Crystal kedua UNSTABLE
↓
SEMUA DPS Crystal kedua
```

### 3. Phase 2 jangan asal Focus

```text
Focus
↓
Vendetta
↓
Death's Door
↓
5 Vendetta
↓
Instant Death
```

Dan selalu ingat:

> **Player mati = Gramiel heal 750k + damage naik.**

Jadi di Ultra Gramiel, **survive dan menjalankan mechanic dengan benar lebih penting daripada greed DPS.**
