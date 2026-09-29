# Panduan Melawan Grim Challenge — AQW

> **Grim Challenge** adalah challenge fight di `/join grimchallenge` melawan **Mechabinky & Raxborg 2.0**.
>
> Panduan ini dibuat berdasarkan riset pada **AQWorlds Wiki, AQWorlds Design Notes/Balance Patch Notes, AQW community guide**, dan video battle guide yang secara khusus membahas fight ini.
>
> **Catatan penting:** data lama tentang boss ini masih dapat ditemukan di beberapa database. Pada **balance update 2026**, AQW mengubah beberapa behavior Mechabinky & Raxborg; salah satunya boss **tidak lagi menggunakan Batara Kala's Devour skill**. Jadi panduan ini membedakan mekanik yang masih relevan dari mekanik lama. 

---

# 1. Apa Itu Grim Challenge?

Grim Challenge adalah challenge boss di map:

```text
/join grimchallenge
```

Boss:

```text
Mechabinky & Raxborg 2.0
```

Stat dasar:

- **Level:** 100
- **Difficulty:** 5 stars
- **HP:** 50,000,000
- **Room limit:** 7 pemain
- Akses hanya untuk **Level 100**
- Harus menyelesaikan **The Gaol of Eternal Torment and Misery** terlebih dahulu. citeturn1search0turn1search1

Fight ini bukan Ultra Boss 4-player seperti Ultra Nulgath atau Ultra Speaker.

Ini adalah **Challenge Boss** dengan room yang dapat menampung sampai 7 pemain. AQW sendiri mengelompokkan challenge boss sebagai fight high-level dengan party yang direkomendasikan. citeturn0search0turn1search7

---

# 2. Cara Membuka Grim Challenge

Kamu tidak bisa langsung masuk jika belum memenuhi requirement.

Checklist:

```text
Level 100
   ↓
Selesaikan The Gaol of Eternal Torment and Misery
   ↓
Pergi ke /join grimchallenge
```

AQW Wiki mencatat `/grimchallenge` hanya dapat diakses player level 100 yang sudah menyelesaikan **The Gaol of Eternal Torment and Misery**. citeturn1search1

---

# 3. Reward dan Weekly Quest

Mort memiliki quest:

## 2.0 No!

Quest:

```text
2.0 No!
```

Requirement:

```text
Mechabinky & Raxborg 2.0 Defeated ×1
```

Reward:

- **1,000,000 Gold**
- **12,500 Grimskull Trolling Rep**
- 0 EXP

Quest ini dapat diselesaikan **sekali per minggu**. citeturn1search2

---

# 4. Gambaran Besar Fight

Mechabinky & Raxborg 2.0 mempunyai banyak breakpoint.

Mental model paling mudah:

```text
100%
 ↓
Devastator Beam
 ↓
90%
 ↓
Contrarium
 ↓
80%
 ↓
Stat Steal
 ↓
70%
 ↓
Consume
 ↓
60%
 ↓
Dracopyre Dive
 ↓
50%
 ↓
Enrage
 ↓
40%
 ↓
Unleashed Chaos
 ↓
30%
 ↓
Summon Legion Mages
 ↓
20%
 ↓
Voice of the Sea
 ↓
10%
 ↓
Self Destruct
 ↓
0%
```

Jadi fight ini bukan:

```text
4 DPS → spam skill → mati
```

Melainkan:

```text
BREAKPOINT
+
DEBUFF
+
VIGIL
+
TAUNT
+
SURVIVAL
+
DPS
```

---

# 5. Boss Shield

Mechabinky & Raxborg 2.0 memiliki Boss Shield.

Damage di atas:

**200,000 per hit**

mengalami diminishing return.

Secara sederhana:

```text
≤ 200k
→ damage normal

> 200k
→ excess damage dikurangi
```

Formula menggunakan exponent **0.8**, dan hasil akhirnya tidak dikurangi sampai di bawah 200,000. citeturn2search0

Artinya:

> Jangan menganggap satu giant burst akan menghapus HP boss.

Sustained DPS lebih penting.

---

# 6. Kematian Player Sangat Mahal

Jika Mechabinky & Raxborg 2.0 membunuh player:

```text
Boss
 ↓
heal 1,000,000 HP
 +
+25% Crit Damage
```

Bonus Crit Damage tersebut:

> **stack tanpa batas.**

Jadi:

```text
1 death
→ +1m HP
→ +25% Crit Damage

2 deaths
→ +2m HP
→ +50% Crit Damage

3 deaths
→ +3m HP
→ +75% Crit Damage
```

dan seterusnya.

citeturn2search0

## Kesimpulan

> **Jangan greed DPS sampai mati.**

Satu death bukan cuma kehilangan satu player.

Boss juga menjadi lebih kuat.

---

# 7. Skill Lock

Boss mempunyai mechanic:

**Skill Locked**

Efek:

> Skill terakhir yang digunakan player dapat dikunci selama beberapa menit.

Artinya ada situasi ketika:

```text
Kamu menggunakan skill penting
        ↓
Skill Locked
        ↓
skill tidak tersedia
```

Karena itu:

> Jangan asal spam skill yang sangat penting untuk survival/rotation.

AQW Wiki mencatat Skill Locked sebagai ability boss. citeturn2search0

---

# 8. PHASE / BREAKPOINT 100% — Devastator Beam

Pada awal fight, boss menggunakan:

**Devastator Beam**

Mekanik penting:

> Damage dapat dibagi berdasarkan jumlah player dalam party.

Artinya:

```text
1 player
→ damage besar ke target

4 player
→ damage terbagi

7 player
→ damage terbagi lagi
```

AQW Wiki mencatat Devastator Beam digunakan pada **100% HP** dan damage-nya dapat dibagi berdasarkan jumlah anggota party. citeturn1search0

## Tips

Jangan memulai fight dengan player sendirian jika memang strategi party mengandalkan damage split.

---

# 9. PHASE 90% — Contrarium

Pada sekitar:

**90% HP**

boss menggunakan:

**Contrarium**

Damage:

> **60% current HP**

Kemudian memberikan:

**Contrarium**

Efek:

> Healing Intake berkurang **200% selama 4 detik**.

citeturn2search0

---

# 10. Kenapa Contrarium Berbahaya?

Misalnya:

```text
HP kamu = 10,000
```

Contrarium:

```text
60% current HP
≈ 6,000 damage
```

Sisa:

```text
≈ 4,000 HP
```

Masalahnya:

```text
Healing Intake -200%
```

berarti healing pada window tersebut sangat terganggu.

## Jangan panik heal

Lebih baik:

```text
Contrarium
↓
survive
↓
tunggu debuff selesai
↓
healing normal kembali
```

---

# 11. PHASE 80% — Stat Steal

Pada:

**80% HP**

boss menggunakan:

```text
Meow
↓
2 second charge
↓
Stat Steal
```

Stat Steal:

- **49% Max HP true damage**
- tidak dapat miss
- tidak dapat crit
- AoE 7

citeturn2search0

---

# 12. Stat Steal Debuff

Player yang terkena:

**Stats Stolen**

mendapat:

- Dodge -10%
- Outgoing Damage -10%
- Crit Chance -10%
- Crit Damage -10%

Durasi:

**25 detik**

Stack:

**hingga 10**

citeturn2search0

---

# 13. Jangan Biarkan Semua Player Kena Stat Steal

Setiap player yang terkena juga memberi boss:

**Stolen Stats**

yang meningkatkan:

- Dodge +10%
- Outgoing Damage +10%
- Crit Chance +10%
- Crit Damage +10%

untuk setiap player yang terkena.

citeturn2search0

Jadi:

```text
4 player terkena
↓
Boss +40% stat terkait
```

Secara praktis:

> Semakin banyak player yang terkena, semakin buruk.

---

# 14. PHASE 70% — Consume

Pada:

**70% HP**

boss melakukan:

```text
BLEEEEEEEEEEEECCH
↓
2 second charge
↓
Consume
```

Consume:

- 2,500 true damage
- AoE 7
- Haste -50%
- Outgoing Damage -80%
- Incoming Damage +100%
- Durasi 10 detik
- Decay 5 detik

citeturn2search0

---

# 15. Consume Sangat Berbahaya

Jika terkena:

```text
Consumed
```

kamu:

```text
lebih lambat
+
damage turun 80%
+
damage masuk naik 100%
```

Artinya:

> **Jangan berdiri sembarangan ketika Consume akan terjadi.**

---

# 16. PHASE 60% — Dracopyre Dive

Pada:

**60% HP**

boss menggunakan:

**Dracopyre Dive**

Damage:

> **Current HP - 1**

Jadi secara konsep:

```text
10,000 HP
↓
9,999 damage

1 HP tersisa
```

Damage ini:

- True Damage
- tidak dapat crit
- mengabaikan Focus
- boss mendapatkan healing berdasarkan jumlah target yang terkena

citeturn2search0

---

# 17. Jangan Salah Memahami Dracopyre Dive

Ini bukan:

```text
"serangan 99%"
```

Tetapi:

```text
Current HP - 1
```

Jadi kamu biasanya akan berada pada:

```text
1 HP
```

setelah terkena.

## Apa yang harus dilakukan?

```text
Dracopyre Dive
       ↓
survive
       ↓
HEAL
       ↓
continue
```

Jangan panik.

---

# 18. Fokus Utama Dracopyre Dive

Boss mendapatkan healing untuk setiap target yang terkena.

Maka:

```text
lebih banyak target
↓
lebih banyak boss heal
```

Ini membuat positioning dan jumlah target yang terkena menjadi penting.

---

# 19. PHASE 50% — Enrage

Pada:

**50% HP**

boss menggunakan:

**Enrage**

Efek:

> Outgoing Damage +100%

dan:

> Semua skill menjadi critical.

citeturn2search0

Ini adalah salah satu titik di mana fight mulai menjadi jauh lebih berbahaya.

---

# 20. Setelah 50% — Jangan Greed

Mulai 50%:

```text
Boss damage ↑
Crits ↑
```

Jika party sebelumnya sudah mempunyai beberapa death:

```text
Crit Damage boss ↑
```

Maka kombinasi:

```text
Enrage
+
death stacks
+
debuff
```

dapat membuat boss sangat berbahaya.

---

# 21. PHASE 40% — Unleashed Chaos

Pada:

**40% HP**

boss menggunakan:

**Unleashed Chaos**

Efek:

- Dodge +60%
- Haste +100%

citeturn2search0

---

# 22. Kenapa 40% Menjadi Masalah?

Boss:

```text
Dodge +60%
+
Haste +100%
```

Artinya:

```text
serangan lebih sering
+
lebih sulit terkena
```

Jangan heran kalau DPS tiba-tiba turun.

---

# 23. PHASE 30% — Summon Legion Mages

Pada:

**30% HP**

boss mulai:

```text
Summon Legion Mages
```

Charge:

**10 detik**

Jika selesai:

```text
Energy Blast
```

Kemudian boss mendapatkan:

**Might of the Legion**

Efek:

- Crit Chance +30%
- Damage +100%
- Hit Chance +130%
- durasi 120 detik

citeturn2search0

---

# 24. Blood Price

Energy Blast memberikan:

**Blood Price**

kepada boss.

Efek:

> Defense -30% selama 20 detik.

Dan:

> dapat stack.

Ini merupakan window yang dapat dimanfaatkan untuk memberikan damage lebih besar.

Jadi setelah Energy Blast:

```text
Boss defense ↓
↓
DPS window
```

---

# 25. PHASE 20% — Voice of the Sea

Ini adalah salah satu mekanik PALING PENTING.

Pada:

**20% HP**

boss menggunakan:

```text
Call of the Sea
↓
5 second charge
↓
Voice of the Sea
```

Voice of the Sea:

> **95% current HP**

AoE:

**7**

citeturn2search0

---

# 26. VIGIL

Voice of the Sea memiliki mechanic khusus.

Jika **Vigil tidak aktif**:

Player terkena:

### Bad Dreams

- Hit Chance -5000%
- Haste -5000%
- 10 detik

dan:

### Nightmare

- Defense -50% pada stack pertama
- Defense -5000% pada stack kedua
- 30 detik

citeturn2search0

---

# 27. Kalau Vigil Aktif

Jika **Vigil aktif**, Voice of the Sea justru memberikan:

**Vigilant**

Efek:

- Crit Chance +25%
- Haste +25%
- 35 detik

citeturn2search0

Jadi:

```text
Vigil OFF
↓
Bad Dreams
+
Nightmare
↓
BAD

Vigil ON
↓
Vigilant
↓
BUFF
```

---

# 28. Inilah Alasan Vigil Sangat Penting

Community battle guide Grim Challenge secara khusus menggunakan **Vigil** untuk menghadapi mechanic Voice of the Sea.

Contoh class setup yang ditunjukkan dalam guide:

```text
Legion Revenant
ArchPaladin
Vigil
Lord of Order
```

atau variasi lain dengan:

- Verus DoomKnight
- Chaos Avenger
- Legendary Hero
- LightCaster

sementara **Legion Revenant + ArchPaladin** melakukan rotating taunt dengan Scroll of Enrage. citeturn1youtube16

---

# 29. Jadi Apa Itu Vigil?

Vigil adalah buff/item yang perlu dipastikan aktif ketika:

```text
20% HP
↓
Voice of the Sea
```

Jika timing salah:

```text
Voice of the Sea
↓
Vigil tidak aktif
↓
Bad Dreams
↓
Nightmare
↓
party bisa kehilangan kemampuan menyerang/bertahan
```

---

# 30. Cara Bermain di 20%

Ketika boss mendekati:

```text
25%
```

mulai bersiap.

```text
25%
↓
jangan panic DPS
↓
prepare Vigil
↓
20%
↓
Call of the Sea
↓
5 sec
↓
Voice of the Sea
↓
VIGIL ACTIVE
```

---

# 31. PHASE 10% — Self Destruct

Ini adalah final mechanic.

Pada:

**10% HP**

boss berkata:

> **SYSTEMS CRITICAL: INITIATING SELF DESTRUCT SEQUENCE IN 10 SECONDS!**

Kemudian:

```text
Self Destruct Initiated
↓
15 second charge
↓
Self Destruct
↓
INSTANT DEATH
```

citeturn2search0

---

# 32. Jangan Berhenti DPS di 10%

Berbeda dengan beberapa Ultra Boss:

> Self Destruct bukan mechanic yang harus ditank.

Kamu harus:

```text
10%
↓
FULL DPS
↓
KILL
↓
sebelum Self Destruct
```

Boss juga mendapatkan:

**Defenses Critical**

yang:

- Dodge -100%
- Damage Resistance -100%

selama charge.

citeturn2search0

Jadi 10% sebenarnya merupakan:

> **FINAL DPS RACE.**

---

# 33. Urutan Lengkap Boss

Gunakan tabel ini sebagai cheat sheet.

| HP | Mechanic | Apa yang dilakukan |
|---:|---|---|
| 100% | Devastator Beam | Party split damage |
| 90% | Contrarium | Survive + tunggu heal window |
| 80% | Stat Steal | Kurangi jumlah target terkena |
| 70% | Consume | Hindari/bertahan |
| 60% | Dracopyre Dive | Siap heal setelah jatuh ke 1 HP |
| 50% | Enrage | Jangan greed |
| 40% | Unleashed Chaos | Antisipasi dodge + haste |
| 30% | Legion Mages | Siap menghadapi 10s charge |
| 20% | Voice of the Sea | **VIGIL WAJIB** |
| 10% | Self Destruct | **FULL DPS** |

---

# 34. Taunt

Community battle guide merekomendasikan **Legion Revenant + ArchPaladin** sebagai rotating taunter menggunakan:

**Scroll of Enrage**

sementara player lain menjalankan role support/DPS sesuai composition. citeturn1youtube16

Contoh:

```text
LR → Taunt
↓
AP → Taunt
↓
LR → Taunt
↓
AP → Taunt
```

Namun timing exact harus mengikuti rotation yang dipakai party.

---

# 35. Jangan Semua Player Spam Taunt

Salah.

Taunt seharusnya:

```text
Taunter A
      ↓
Taunter B
      ↓
Taunter A
      ↓
Taunter B
```

bukan:

```text
7 player
↓
7 orang spam Enrage
```

Karena tujuan taunt adalah mengontrol siapa yang menerima mechanic tertentu.

---

# 36. Party Composition yang Praktis

Salah satu setup yang ditunjukkan community guide:

```text
Legion Revenant
ArchPaladin
Vigil
Lord of Order
```

Dengan:

```text
LR + AP
→ rotating taunt
```

dan:

```text
Vigil
→ menangani Voice of the Sea
```

citeturn1youtube16

---

# 37. Variasi Class

Community guide juga mencantumkan class yang dapat digunakan dalam variasi setup:

- Vigil
- Lord of Order
- Verus DoomKnight
- Chaos Avenger
- Legendary Hero
- LightCaster
- Legion Revenant
- ArchPaladin

citeturn1youtube16

Jangan menganggap daftar tersebut sebagai satu-satunya party yang valid.

Yang penting adalah:

```text
Taunt
+
Vigil
+
Support
+
DPS
+
survival
```

---

# 38. Role Breakdown

## Legion Revenant

Fungsi:

- DPS
- support
- taunt
- utility

Dalam setup guide:

> LR adalah salah satu rotating taunter.

---

## ArchPaladin

Fungsi:

- defensive support
- damage reduction
- healing
- taunt

Dalam setup guide:

> AP menjadi pasangan taunt LR.

---

## Lord of Order

Fungsi:

- support
- buff
- heal
- party utility

---

## Vigil

Fungsi:

> Menjawab mechanic Voice of the Sea.

Ini bukan sekadar class untuk DPS.

---

## Verus DoomKnight

Dapat digunakan sebagai DPS/utility dalam variasi setup.

---

## Chaos Avenger

Dapat digunakan sebagai DPS/tank/utility.

---

## Legendary Hero

Dapat berfungsi sebagai support/utility.

---

## LightCaster

Dapat berfungsi sebagai support/DPS.

---

# 39. AoE dan Positioning

Boss mempunyai banyak serangan:

```text
AoE 4
AoE 7
AoE 30
```

Jadi jangan menganggap:

> "Semua orang berdiri di satu titik pasti aman."

Beberapa mechanic memang dirancang untuk mengenai sejumlah target.

---

# 40. Fokus pada HP Percentage

Jangan hanya melihat cooldown.

Untuk Grim Challenge:

> **HP boss adalah timer mechanic.**

Contoh:

```text
Boss 82%
↓
bersiap Stat Steal

Boss 72%
↓
bersiap Consume

Boss 62%
↓
bersiap Dracopyre Dive

Boss 52%
↓
bersiap Enrage

Boss 42%
↓
bersiap Unleashed Chaos
```

Ini lebih berguna daripada hanya melihat skill bar.

---

# 41. Strategy 100% → 80%

```text
START
 ↓
Party masuk
 ↓
Devastator Beam
 ↓
90%
 ↓
Contrarium
 ↓
90→80
 ↓
prepare Stat Steal
 ↓
80%
```

Tujuan:

> jangan kehilangan player terlalu awal.

---

# 42. Strategy 80% → 60%

```text
80%
 ↓
Stat Steal
 ↓
70%
 ↓
Consume
 ↓
60%
 ↓
Dracopyre Dive
```

Prioritas:

```text
survive
>
damage
```

---

# 43. Strategy 60% → 40%

```text
60%
 ↓
Dracopyre Dive
 ↓
heal
 ↓
50%
 ↓
Enrage
 ↓
40%
 ↓
Unleashed Chaos
```

Mulai 50%:

> Jangan main terlalu agresif.

---

# 44. Strategy 40% → 20%

```text
40%
 ↓
Unleashed Chaos
 ↓
30%
 ↓
Legion Mages
 ↓
20%
 ↓
VOICE OF THE SEA
```

Pada 30%:

```text
siapkan Vigil
```

---

# 45. Strategy 20% → 0%

```text
20%
 ↓
Call of the Sea
 ↓
5 sec
 ↓
Voice of the Sea
 ↓
Vigil
 ↓
10%
 ↓
Self Destruct
 ↓
FULL DPS
 ↓
KILL
```

---

# 46. Mekanik Paling Berbahaya

Jika harus mengurutkan berdasarkan **fungsi mechanic**, ada beberapa yang wajib dihafalkan:

## #1 — Voice of the Sea

Karena salah Vigil dapat menghancurkan kemampuan party.

```text
20%
↓
Vigil
```

---

## #2 — Self Destruct

```text
10%
↓
15 sec
↓
INSTANT DEATH
```

Harus DPS race.

---

## #3 — Dracopyre Dive

```text
Current HP - 1
```

Kamu akan jatuh ke 1 HP.

---

## #4 — Stat Steal

```text
49% max HP
+
stat debuff
+
boss stat buff
```

---

## #5 — Death

```text
Boss +1m HP
+
+25% Crit Damage
```

---

# 47. Kesalahan Paling Umum

## ❌ 1. Tidak membawa Vigil

Masalah:

```text
20%
↓
Voice of Sea
↓
Bad Dreams
+
Nightmare
```

---

## ❌ 2. Vigil terlambat

Vigil harus aktif saat Voice of the Sea resolve.

Jangan baru menyalakannya setelah terkena debuff.

---

## ❌ 3. Semua orang terkena Stat Steal

Boss mendapat Stolen Stats berdasarkan jumlah target.

---

## ❌ 4. Panik setelah Dracopyre Dive

HP menjadi 1.

Itu memang mechanic.

```text
1 HP
↓
heal
```

---

## ❌ 5. Greed setelah 50%

Boss mulai Enrage.

---

## ❌ 6. Menganggap 30% aman

Justru ada:

```text
Legion Mages
↓
Might of Legion
```

---

## ❌ 7. Berhenti DPS pada 10%

Salah.

```text
10%
↓
SELF DESTRUCT
↓
FULL DPS
```

---

## ❌ 8. Player mati berkali-kali

Setiap kill:

```text
Boss +1m HP
+
+25% Crit Damage
```

stack.

---

# 48. Checklist Sebelum Masuk

## Requirement

- [ ] Level 100
- [ ] Selesai The Gaol of Eternal Torment and Misery
- [ ] Bisa masuk `/grimchallenge`

## Party

- [ ] Taunter tersedia
- [ ] Scroll of Enrage tersedia
- [ ] Vigil tersedia
- [ ] Support tersedia
- [ ] DPS cukup

## Mechanic

- [ ] Tahu 90% Contrarium
- [ ] Tahu 80% Stat Steal
- [ ] Tahu 70% Consume
- [ ] Tahu 60% Dracopyre Dive
- [ ] Tahu 50% Enrage
- [ ] Tahu 40% Unleashed Chaos
- [ ] Tahu 30% Legion Mages
- [ ] Tahu 20% Voice of Sea + Vigil
- [ ] Tahu 10% Self Destruct

---

# 49. Cheat Sheet Party

Kirim ini ke party sebelum pull:

```text
GRIM CHALLENGE

100% → Devastator Beam
90%  → Contrarium
80%  → Stat Steal
70%  → Consume
60%  → Dracopyre Dive
50%  → Enrage
40%  → Unleashed Chaos
30%  → Legion Mages
20%  → VOICE OF SEA → VIGIL
10%  → SELF DESTRUCT → FULL DPS

TAUNT:
LR ↔ AP

IMPORTANT:
- Don't die.
- Death = boss +1m HP +25% Crit Damage.
- Vigil must be active for Voice of Sea.
- Dracopyre Dive leaves you at ~1 HP.
- Don't panic at 10%; kill boss before Self Destruct.
```

---

# 50. Flowchart

```text
                    START
                      │
                      ▼
              DEVASTATOR BEAM
                      │
                      ▼
                    90%
                      │
                CONTRARIUM
                      │
                      ▼
                    80%
                      │
                 STAT STEAL
                      │
                      ▼
                    70%
                      │
                    CONSUME
                      │
                      ▼
                    60%
                      │
              DRACOPYRE DIVE
                      │
                  HP → 1
                      │
                    HEAL
                      │
                      ▼
                    50%
                      │
                   ENRAGE
                      │
                      ▼
                    40%
                      │
               UNLEASHED CHAOS
                      │
                      ▼
                    30%
                      │
                LEGION MAGES
                      │
                      ▼
                    20%
                      │
               CALL OF THE SEA
                      │
                   5 seconds
                      │
               VOICE OF THE SEA
                      │
                 VIGIL ACTIVE
                      │
                      ▼
                    10%
                      │
               SELF DESTRUCT
                      │
                  15 seconds
                      │
                      ▼
                 FULL DPS!!!
                      │
                      ▼
                   VICTORY
```

---

# 51. Versi Bahasa Bayi

Kalau semua mechanic di atas terlalu banyak, hafalkan ini:

```text
100%
→ mulai

90%
→ jangan panik heal

80%
→ jangan semua kena

70%
→ hati-hati debuff

60%
→ HP jadi 1
→ heal

50%
→ boss makin sakit

40%
→ boss makin cepat

30%
→ siap-siap

20%
→ VIGIL WAJIB

10%
→ BUNUH SECEPATNYA
→ jangan tunggu boom
```

---

# 52. Tiga Aturan Utama

Kalau cuma mau mengingat 3 hal:

## 1. Jangan mati

Karena:

```text
death
↓
boss +1,000,000 HP
↓
+25% Crit Damage
```

---

## 2. Vigil di 20%

```text
20%
↓
Voice of Sea
↓
VIGIL
```

Kalau Vigil gagal:

```text
Bad Dreams
+
Nightmare
```

---

## 3. 10% = DPS RACE

```text
10%
↓
Self Destruct
↓
15 sec
↓
INSTANT DEATH
```

Jadi:

> **BUNUH BOSS.**

---

# 53. Catatan Update 2026

Ini penting karena beberapa guide lama masih beredar.

Pada **Balance Update AQW 2026**, Artix Entertainment mencatat:

> **Mechabinky & Raxborg no longer use Batara Kala's Devour skill.**

Jadi jika kamu menemukan guide lama yang menjadikan:

```text
Devour
↓
anti-heal
↓
DoT
```

sebagai mechanic utama Grim Challenge, jangan langsung menganggap itu masih berlaku.

Gunakan behavior terbaru sebagai acuan. citeturn1search6

---

# 54. Sumber Riset

## AQW Wiki — Grim Challenge

https://aqwwiki.wikidot.com/grim-challenge

Untuk:

- lokasi
- room limit
- level requirement
- akses map

citeturn1search1

---

## AQW Wiki — Mechabinky & Raxborg 2.0

https://aqwwiki.wikidot.com/mechabinky-raxborg-2-0

Untuk:

- HP
- Boss Shield
- seluruh breakpoint
- damage
- debuff
- Vigil interaction
- Self Destruct
- death penalty

citeturn2search0

---

## AQW Wiki — Mort's Quest

https://aqwwiki.wikidot.com/mort-s-quest

Untuk:

- quest **2.0 No!**
- weekly restriction
- 1,000,000 Gold
- 12,500 Grimskull Trolling Rep

citeturn1search2

---

## AQWorlds Official — Grimskull's Gaol

https://www.aq.com/gamedesignnotes/aqw-09nov23-grimskullgaol-9375

Untuk:

- pembukaan Gaol of Eternal Torment and Misery
- requirement level 80 untuk dungeon
- requirement Smite
- Scythe of Azalith
- weekly challenge boss

citeturn0search1

---

## AQWorlds Official — Balance Patch Notes

https://www.aq.com/gamedesignnotes/AQW-Balance-PatchNotes-9515

Untuk update 2026 yang mengubah behavior Mechabinky & Raxborg, termasuk:

- boss tidak lagi menggunakan **Batara Kala's Devour**

citeturn1search6

---

## AQW Community Battle Guide — MrGoon

**AQW How To Beat MechaBinky + Raxborg 2.0**

https://www.youtube.com/watch?v=IE8XyxcVxNE

Digunakan untuk cross-check:

- class setup
- rotating taunt
- Scroll of Enrage
- Vigil
- party composition

Guide tersebut secara eksplisit menunjukkan **Legion Revenant + ArchPaladin** sebagai rotating taunter dan class seperti Vigil, Lord of Order, Verus DoomKnight, Chaos Avenger, Legendary Hero, serta LightCaster sebagai pilihan setup. citeturn1youtube16

---

# 55. FINAL CHEAT SHEET

```text
╔══════════════════════════════════════════╗
║             GRIM CHALLENGE              ║
║       MECHABINKY & RAXBORG 2.0          ║
╠══════════════════════════════════════════╣
║ 100% → DEVASTATOR BEAM                  ║
║ 90%  → CONTRARIUM                       ║
║ 80%  → STAT STEAL                       ║
║ 70%  → CONSUME                          ║
║ 60%  → DRACOPYRE DIVE → HP ~1           ║
║ 50%  → ENRAGE                           ║
║ 40%  → UNLEASHED CHAOS                 ║
║ 30%  → LEGION MAGES                    ║
║ 20%  → VOICE OF SEA → VIGIL             ║
║ 10%  → SELF DESTRUCT → FULL DPS        ║
╠══════════════════════════════════════════╣
║ DEATH:                                  ║
║ Boss +1,000,000 HP                      ║
║ Boss +25% Crit Damage                   ║
╠══════════════════════════════════════════╣
║ PARTY:                                  ║
║ LR ↔ AP = rotating taunt                ║
║ Vigil = Voice of Sea                    ║
║ LoO = support                            ║
║ DPS = finish boss                       ║
╚══════════════════════════════════════════╝
```

---

# 56. Inti Grim Challenge

Grim Challenge sebenarnya dapat dibuat sangat sederhana di kepala:

```text
BOSS HP
   │
   ├── 80% → jangan semua kena Stat Steal
   │
   ├── 60% → HP jadi 1 → HEAL
   │
   ├── 50% → boss ENRAGE
   │
   ├── 30% → Legion Mages
   │
   ├── 20% → VIGIL
   │
   └── 10% → KILL BEFORE BOOM
```

Dan satu aturan yang selalu berlaku:

> **Jangan mati.**

Karena setiap kematian membuat boss mendapatkan **1,000,000 HP kembali + 25% Crit Damage**, dan bonus Crit Damage tersebut dapat terus menumpuk. citeturn2search0

---

## Ringkas banget

```text
/join grimchallenge

LV 100
+
DONE GRIM GAOL
+
PARTY

LR ↔ AP
TAUNT

VIGIL
→ 20%

DRACOPYRE
→ HP 1
→ HEAL

10%
→ SELF DESTRUCT
→ FULL DPS
→ KILL
```

**Itulah inti Grim Challenge yang perlu kamu kuasai sebelum mencoba farm weekly.**
