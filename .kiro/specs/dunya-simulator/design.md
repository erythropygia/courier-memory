# Tasarım: Dünya ve simülatör

## Uygulamada netleşen kararlar (ilk taslağa göre)

1. **Kurye becerisi** bilgiye bağlı başarısızlık bileşeninin tamamını ölçekler (taban + navigasyon + püf noktası + yanlış ipucu). Becerikli kurye bilmediği adreste de yolunu daha iyi bulur. Böylece beceri veriden tahmin edilebilir olur.
2. **Kapalı türler** (`saturday_closed`, `temporary_closed`): Kurye bunları biliyorsa ya da geçerli bir ipucu aldıysa durağa gitmez; durak **planlı erteleme** olur ve deneme sayılmaz. Bilmiyorsa boşuna gider ve deneme başarısız olur. `lunch_break` biliniyorsa kurye saati kaydırır ve ceza kalkar.
3. **Uyum tahmincisi:**
   - Kuryeden bağımsız "alıcı yok" başarısızlıkları ayrı tutulur (neden kodu sayesinde).
   - Kurye etkisi yalnız kuryeye bağlı başarısızlıklardan ve **blok türü düzeyinde** havuzlanmış oranla standartlaştırılarak tahmin edilir.
   - Gerekçe: Sabit bölgede her bloğa tek kurye gittiği için blok kendi oranıyla standartlaştırılırsa kurye etkisi bölgeden ayrılamaz.
4. **Hafıza iki kaynaktan öğrenir:**
   - kurye notları
   - teslim kayıtları: aynı adreste "kapalı" nedenli başarısızlık, gün/saat örüntüsüyle `saturday_closed`, `lunch_break` ya da `temporary_closed` türüne bağlanır (`ingest_events`)
5. **Geri bildirim** ("hâlâ geçerli mi?") varsayılan olarak açıktır (`memory.feedback: true`). Yanlış ya da bayat ipucu alan kurye, kaydı `p_feedback` olasılıkla düşürür.
6. **Kontrollü öğrenme rotasyonu** P2'ye ertelendi; yapılandırmada yok.
7. **Not düzeyinde "bayat" zorluk yok.** Bayatlık, püf noktası değiştikten sonra hafıza kaydında kendiliğinden oluşur. Notlarda zorluklar: `normal | pii | ambiguous | wrong | noise` (noise: adresle ilgisiz not, kurye-gün başına `notes.noise_rate`).
8. **Sabit bölgeler** ısınmanın gerçekleşen talebinden değil, beklenen talepten (adres oranları) hesaplanır; sonuç aynıdır, daha basittir.
9. **Maliyet:** `w_fail · Σ p̂·n + w_time · Σ t̂` (w_time dakika başınadır, varsayılan 0,05).
10. **Kalibrasyon (saha verisinden türetilmiş toplu hedefler, `sim/config/calibration.yaml`, `python -m cm_sim.calibration`):**
    - **İki adres havuzu:** düzenli adresler (toplu teslim noktaları + adreslerin `recurring_share` kadarı, lognormal talep çeşitliliği) gönderilerin `1 − sporadic_share` kadarını; seyrek adresler (çoğu tek seferlik) kalanını alır. Böylece adres tekrar oranları (1/5/12 gün) ve tek seferlik adres payı sahaya uyar.
    - **Sabit bölgeler gevşek dengelidir** (`fixed_zone_slack`): sahadaki bölgeler mahalle sınırlarıyla çizilmiş ve tarihseldir, iş yükü sapması yüksektir.
    - **Ek kurye:** Bandı aşan sabit bölgenin tur sonundaki durakları "ek kurye" rotalarına aktarılır (yedek, yeni ya da ödünç havuzundan).
11. **Uzun dönem senaryosu** (`long_term.yaml`): 60 iş günü, ayda ~%8 kurye devri, yayılmış izinler, iki kampanya haftası. Snapshot'sız koşulur ve `data/demo_run/long_term/` altına yayımlanır.
12. **Çekirdek bölgeli dinamik plan (C/D), Hungarian eşleştirmenin yerine.**
    - Gerekçe: "Kurye bir bölgede iyiyse neden kaydırıyorsunuz?" sorusu. Dinamik plan kuryeyi değil sınırı ve fazla işi kaydırır.
    - `AnchoredPlanPolicy.plan` çalışma adımları:
      - Kuryenin çekirdeği, tanıdıklığı ≥ `anchor_min_f` olan bloklardan çıkar.
      - Günün talebi çekirdeklere göre puanlanır ve en talepli k çekirdeğin kuryesi çalışır. Eksik kalırsa çekirdeksiz kurye (yedek > kıdemli > yeni > ödünç) esnek kümeye gider.
      - Kapasiteli atamada uzaklıktan `anchor_bonus_km × f` düşülür; tanıdık blok o kuryeye "yakın" sayılır.
      - Küme merkezi `anchor_alpha` oranında çekirdekte kalır.
    - (Faz 1) D, C'nin planını paylaşırdı. **Faz 2'de değişti:** D kendi planını kurar (madde 15); tanıdıklık geçmişleri yine aynıdır, çünkü ziyaretler sonuçtan bağımsızdır.
    - Atama matrisi senaryo soruları için yine dışa aktarılır.
    - Performans puanı kullanılmaz.
13. **Mevcut yapının gerçekçiliği:**
    - Bölgeler eski talebe göre çizilmiştir (`fixed_zone_demand_drift`, blok düzeyinde lognormal kayma).
    - Ek kurye birkaç bölgenin taşan işini bölge sırasıyla toplar (`extra_courier_mode: zones`).
    - Kalibrasyona sahadaki dinamik geçiş farkları eklendi: kurye-gün ve planlanan süreyle vardiya bandı. Toplam 14/14.
    - Km farkı simülasyon coğrafyasında oluşmaz; zorlanmadı.
    - Yeni metrikler: `in_band_planned_share`, `planned_cv`.
14. **Modüller** (Faz 1; Faz 2 eklemeleri madde 15–22'de):
    - `history.py`: gözlemlenebilir geçmiş + `HistoryReader`
    - `policies/simple.py`: `BlindPolicy`, `FitAssignPolicy`
    - `policies/memory_oracle.py`
    - `export.py`, `publish.py` (`data/demo_run/` + `long_term/` + `sweep.json` + `calibration.json`), `sweep.py`, `calibration.py`
15. **Yeni kol E değil, D gerçek yapıldı (Faz 2).** D = "çekirdek bölge + hafıza"; hafıza planı ve rotayı değiştirir.
    - Gerekçe: ekonomi, sunum, demo ve orkestratör hep D'yi kullanır; beşinci kol UI, sweep, ekonomi ve Kiro kitinde her yüzeyi çoğaltırdı. Ayrıştırma kaybolmaz: her D rotası "hafızasız" ve "yalnız ipucu" olarak aynı rastgele sayılarla yeniden yürütülür (karşı-olgu) ve `cm_sim.ablation` bileşenleri tek tek kapatır.
    - `policies/simple.py` `extra_w` (servis düzeltmesinin durak ağırlığı), `policies/memory_oracle.py` `rules_for(...)` (hafızadan durak kuralı) ve `harvest(...)`.
16. **`routing_memory.py` (saf fonksiyonlar):** `StopRule`, `rule_from_entries(entries, weekday, lunch, extra_map, min_sources_closed)`, `plan_route(...)`, `repair_windows`, `arrivals`. Planda erteleme yalnız `routing.defer_min_sources` (2) bağımsız kaynakla: tek kaynaklı "geçici kapalı" kayıtlarının %38'i yanlıştı (kapanış bitmiş, not yanlış adrese bağlanmış). Pencere onarımı or-opt (çıkar, en iyi yere yerleştir); beklenen varış = başlangıç + `routing.time_scale` × geçen planlanan süre.
17. **Öğle arası kestirmesi kaldırıldı:** bilinen öğle arası pencere içinde gelinirse ek dakika `min(pencere sonu − varış, quirks.lunch_wait_max)`; ayrıca bilinen püf noktasının kalan süresi `quirks.effects.*.known_minutes` (VARSAYIM). Servis düzeltmesinin dürüst olması için şart: dünya bilinen püf noktasına süre yazmasaydı planın eklemesi hata olurdu. Yan etki: gerçekleşen vardiya bandı payları düştü (uzun dönem A %38→%33, D %60→%44); planlanan bant ve kalibrasyon (14/14) değişmedi. Yeni başarısızlık nedeni `wrong_deferral` (`outcome.plan_deferred_result`).
18. **Hedef 2 farklılaştırması:** `couriers.py` çok dönemli ödünç; `calendar.borrowed[].border_side/border_depth_km` komşu şubeyle ortak sınır sokaklarının tanıdıklığını üretir (Onur doğu 2 km, Gökhan kuzey 1,2 km, Melis hiç). "Önceki destek günü" denendi ve bırakıldı. Aynı denemede tahminci hatası düzeltildi: kapı hızı yabancı duraklardaki yol bulma dakikasıyla şişiyordu; `engine._execute` artık yalnız tanıdık duraklardan öğrenir. Ödünç/çekirdeksiz kurye sırası `days_in_branch`'e göre (C ve D aynı kural).
19. **Hasat (kol D):** plan sonrası, kıdemlinin gizli bilgisinden cevap (`p_answer`); günde ≤ 30 soru, kıdemli başına ≤ 3, ayrılan kuryeye son 3 gününde devir teslim soruları (`rng.S_HARVEST` akışı, `history.addr_days`). Atama matrisi hasattan önceki, `memory/{gün}` hasattan sonraki hafızadır.
20. **Karşı-olgu:** `engine` her D rotasını üç kez yürütür (hafızasız / yalnız ipucu / hafızalı); `SimResult.counterfactuals`. Karşı-olgu kuryenin o günkü bilgisiyle yapılır; bu yüzden "hafıza olmasaydı" düzeyi C'den farklıdır ve Hedef 1'de iki ölçü bulunur (C ↔ D ve aynı rota).
21. **Hedef 1 ve ablasyon modülleri:** `learning.py` (senaryo `hiring`, 12 seed, ustalaşma eşiği kıdemli × 1,1, ilk hafta 6 iş günü; ProcessPool) ve `ablation.py` (VARIANTS: `hint_only` = `routing.enabled=false` + `memory.harvest_per_day=0`, `hint_harvest`, `hint_route`, `full`).
22. **Dışa aktarım ve demo günü:** `export.py`: D anlık görüntüsünde `plan` ve `counterfactual`, `summary.memory_routing`, `learning_curve.same_route`, `harvest.json`, `meta.critical.memory_gain`. `critical_moment` öncelik sırası: "kim gitsin" seçiminin yapıldığı gün (gelebilecek ödünç > kullanılan) > ödünç > yeni > yedek; sonra ipucu × yabancılık (gün 32, kurye Gökhan korundu).

## Genel bakış

`cm_sim` saf Python + numpy/scipy ile yazılmış, deterministik, tek süreçli bir ayrık gün simülatörüdür. LLM çağrısı yapmaz. Üç rolü vardır:

1. **Demo verisi üretir:** Harita, kuryeler, rotalar, notlar.
2. **Kolları karşılaştırır:** Ana tablo, öğrenme eğrisi, sağlamlık taraması.
3. **Ajanlara araç sağlar:** Uyum tahmincisi, atama çözücü, rota/varış saati hesabı.

```
            ┌────────────── gizli gerçek (yalnız sonuç modeli + değerlendirme) ──────────────┐
            │  Block.difficulty   Address.quirks   Courier.skill/speed/note_propensity       │
            └────────────────────────────────────────────────────────────────────────────────┘
 config ─► world ─► demand(gün) ─► planning ─► AssignmentPolicy ─► MemoryPolicy.hints ─► outcome ─► learning/notes ─► MemoryPolicy.ingest ─► metrics
                                  (kol A: sabit   (A: sabit, B: rastgele,   (yalnız D)            (CRN)       (tanıdıklık,          (yalnız D)
                                   bölge; B/C/D:   C/D: uyum+Hungarian)                                          püf öğrenme, not)
                                   ortak kümeler)
```

**Gün döngüsü:**
- **Isınma:** Önce N_warm gün yalnız kol A koşar. Kuryeler kendi bölgelerini öğrenir, gözlemlenebilir geçmiş oluşur.
- **Değerlendirme:** Durum `deepcopy` ile dört kola çatallanır ve her kol N_eval gün koşar.

**Ortak kümeler:** B ve C kollarında planlama kuryeden bağımsız olduğu için kümeler ve rotalar o gün **bir kez** hesaplanır ve paylaşılır. Faz 2'den beri **D bu paylaşımın dışındadır**: D hafızayı kullanarak kendi planını kurar (`routing_memory`); aynı rastgele sayılar sayesinde fark yine yalnızca atama, hafıza ve rotadan gelir. D'nin düz sırası (`plan.plain_order`) ve karşı-olgu yürütmeleri ayrıştırmayı sağlar.

## Veri modeli

Gizli gerçek ile gözlemlenebilir veri farklı sınıflardadır. Politikalar yalnızca `*View` nesnelerini görür.

```python
# --- gizli gerçek (cm_sim.world / cm_sim.couriers) ---
@dataclass
class Block:          id: BlockId; row: int; col: int; kind: BlockKind; difficulty: float; center: LatLng
@dataclass
class Quirk:          id: QuirkId; kind: QuirkKind; version: int; active_from: int; active_to: int | None
@dataclass
class Address:        id: AddressId; block: BlockId; kind: AddressKind; latlng: LatLng; quirks: list[Quirk]
@dataclass
class Courier:        id: CourierId; kind: CourierKind; skill: float; speed: float; note_propensity: float
                      home_zone: ZoneId | None; calendar: Calendar
                      known_quirks: dict[tuple[AddressId, QuirkId], int]   # → bilinen sürüm

# --- gözlemlenebilir (politikalar ve ajanlar bunları alır) ---
@dataclass(frozen=True)
class StopView:       id: StopId; address: AddressId; block: BlockId; latlng: LatLng; n_shipments: int; eta_min: int | None
@dataclass(frozen=True)
class ClusterView:    id: ClusterId; stops: tuple[StopView, ...]; planned_minutes: float; km: float
@dataclass(frozen=True)
class CourierView:    id: CourierId; kind: CourierKind; available: bool; days_in_branch: int
@dataclass(frozen=True)
class DayContext:     day: int; weekday: int; history: HistoryReader; memory: MemoryReader | None
```

**`HistoryReader`** gözlemlenebilir geçmişe salt-okur erişim verir:
- kurye×blok ziyaret sayıları
- son ziyaret günü
- kurye×blok deneme/başarısızlık sayıları
- blok bazında toplam deneme/başarısızlık

Tanıdıklık ziyaret geçmişinden hesaplandığı için gözlemlenebilirdir. Kuryenin hangi püf noktasını bildiği ise **gizlidir**.

## Algoritmalar

### Coğrafya (`world.py`)

- **Koordinat sistemi:** Koordinatlar soyuttur. Varsayılan kutu (39,00 K, 35,00 D) merkezli ~12×10 km'lik bir alandır. Arayüzde altlık harita varsayılan olarak kapalıdır, blok ızgarası haritanın kendisidir. Altlık açılırsa noktalar gerçek yerleşimle örtüşmez; bu bilinçli bir tercihtir.
- **Blok türleri:** Merkezden uzaklığa göre katmanlıdır:
  - çekirdek: yoğun konut + iş merkezi
  - orta halka: site + apartman
  - dış halka: kırsal, arada sanayi yamaları
  Halka sınırları düzgün olmasın diye düşük frekanslı gürültü eklenir.
- **Adres dağılımı:** Adres sayısı blok türüne göre dağıtılır. Kırsal blokların çoğu boş ya da çok seyrektir.

### Püf noktaları

Her adrese, adres türüne bağlı olasılıklarla püf noktası atanır. Sürüm (`version`) değişince eski bilgi geçersiz olur.

**Değişim dinamiği:**
- **Kalıcı püf noktalarının değişmesi:** Kalıcı püf noktalarının %`quirks.change_rate` kadarı değerlendirme döneminde bir kez değişir. Değişince sürüm 1 artar.
- **Süreli püf noktaları:** Adreslerin %`quirks.temporary_rate` kadarına süreli püf noktası eklenir. Başlangıç günü rastgeledir, süresi 5–15 gündür.

### Talep (`demand.py`)

**Gönderi sayısı:** Her gün her adres için Poisson(λ_tür × haftagünü_çarpanı × şok_çarpanı) çekilir. Toplu teslim noktalarında λ büyüktür. Gönderisi olan adres o gün bir duraktır.

**Tohum:** Talep günün tohumundan üretilir ve kollardan bağımsızdır.

### Planlama (`planning.py`)

**Sabit bölgeler (kol A):**
- Isınma döneminin ortalama durak yükü (dk) ağırlığıyla, kıdemli kurye sayısı kadar dengeli k-means çalıştırılır.
- Her bölge bir kıdemli kuryeye atanır ve bölgeler sabit kalır.
- Kuryesi olmayan bölge `planning.fixed_absence_rule` kuralına göre ele alınır:
  - `reserve` (varsayılan): Bölge yedek kuryeye verilir.
  - `split`: Bölge komşu bölgelere bölünür.

**Dinamik kümeler (kol B/C/D):**
1. Günün toplam iş yükü servis + tahmini yol olarak hesaplanır. Küme sayısı k = ceil(toplam / `planning.target_minutes`) olur ve [1, müsait kurye] aralığına sıkıştırılır.
2. Dengeli k-means uygulanır: k-means++ başlangıç, ardından kapasiteli atama. Duraklar "pişmanlık" (en yakın iki merkez arası fark) sırasıyla kapasitesi dolmamış en yakın merkeze verilir. En fazla 10 tur.
3. Onarım: Bandı aşan rotanın kenar durakları komşu kümeye taşınır.

**Rota ve süre:**
- Her küme için en yakın komşu + 2-opt (numpy ile vektörize) uygulanır. 2-opt en fazla `planning.two_opt_passes` tur koşar.
- Planlanan süre:
  ```
  dk = Σ (1 + 1,5·n_gönderi) + km_kuşuçuşu × yol_katsayısı × dk_per_km
  ```
- Varış saati (ETA): `planning.start_time` (09:00) itibarıyla kümülatif hesaplanır.

### Atama (`policies/`)

- **A:** Sabit bölge → sabit kurye.
- **B:** Tohumlu rastgele permütasyon. Kollar arası adillik için tohum (seed, gün) ile belirlenir.
- **C/D:** `estimation.expected_cost(courier, cluster, ctx)` ile bir maliyet matrisi kurulur, sonra `scipy.optimize.linear_sum_assignment` çalıştırılır. Matris dikdörtgen olabilir (kurye > küme); atanmayan kurye o gün planlanmaz.

**Maliyet formülü:**
```
cost(c, k) = Σ_{s ∈ k}  w_fail · p̂(c, s)  +  w_time · t̂(c, s) / 60

p̂(c, s) = clip( r̂_alıcıyok(b_s) + r̂_blok(b_s) · ρ̂_c · (1 + η̂ · (1 − f̂_c,b_s) · (1 − relief · m_s)) , 0, 0.95 )
t̂(c, s) = (1 + 1,5·n_s) · v̂_c + nav_dk · (1 − max(f̂_c,b_s , m_s))
```

| Sembol | Anlamı |
|---|---|
| `f̂` | Ziyaret geçmişinden tanıdıklık |
| `m_s` | Durakta hafızada geçerli ve güvenilir kayıt varsa 1, yoksa 0. Yalnız D'de; C'de hep 0. |
| `r̂_blok`, `ρ̂_c` | Tahminciden gelir |
| `v̂_c` | Kuryenin gözlemlenen dk/gönderi oranından büzülmüş hız tahmini |

**Kontrollü öğrenme rotasyonu** (`assignment.learning_rotation`, varsayılan kapalı): Açıldığında her gün en fazla `r` atama, maliyet artışı %`x`'i geçmeyecek şekilde, hafıza kapsamı ≥ θ olan yabancı kümelere zorlanır.

### Uyum tahmincisi (`estimation.py`)

Yöntem dolaylı standartlaştırma ve büzülmedir. Bloğun zorluğu ile kuryenin etkisi ayrılır.

**1. Blok oranı:**
```
r̂_blok(b) = (başarısız_b + α0·r_genel) / (deneme_b + α0)
```

**2. Kurye etkisi (kurye oranı):**
```
ρ̂_c = (gözlenen_başarısız_c + β0) / (Σ_{deneme ∈ c} r̂_blok(b_deneme) + β0)
```
- Bu oran, kuryenin gittiği blokların beklenen başarısızlığına göre hesaplanır.
- Az veride değer 1'e büzülür.
- Değer [0,5, 2,0] aralığına sıkıştırılır.

**3. Doğrulama:** `report_recovery()` iki sıra korelasyonu verir:
- Spearman(ρ̂_c, gerçek beceri)
- Spearman(naif kurye başarısızlık oranı, gerçek beceri)

Naif oran bölge zorluğuyla karışık olduğu için düşük kalmalıdır.

### Sonuç modeli (`outcome.py`)

Durak bir adrestir. Bilgiye bağlı başarısızlık durağın tamamını etkiler: giriş bulunamazsa o duraktaki bütün gönderiler başarısız olur. Alıcı yokluğu ise gönderi düzeyindedir.

```
p_bilgi(c, s, t) = clip( d_b · skill_c · (1 + η · (1 − f_c,b))
                       + Σ_{q ∈ active(s,t), bilinmiyor(c,q) ∧ ¬ipucu_uyuldu(c,s,q)} δ_fail(q)
                       + [yanlış ipucu ya da bayat bilgi] · δ_wrong , 0, 0.95 )

Durak düzeyi:   u_stop  < p_bilgi            → durağın tüm gönderileri başarısız (bilgiyle önlenebilir)
Gönderi düzeyi: u_ship  < p0(adres_türü, t)  → o gönderi başarısız, neden = alıcı yok (önlenemez)
```

**Neden kodu:** `u_cause` ile bileşenlerin payına göre seçilir:
- Navigasyon / blok kaynaklı başarısızlık → "adres bulunamadı"
- `saturday_closed` / `lunch_break` → "kapalı"
- `safety` / `back_entry` → "giriş yapılamadı"
- `position_wrong` → "adres bulunamadı"
- `bell` → "alıcıya ulaşılamadı"

**Kapıda geçen süre:**
```
t = (1 + 1,5·n) · speed_c + nav_dk · (1 − f_c,b) + Σ bilinmeyen τ(q) + Σ bilinen known_minutes(q) + yanlış ipucu τ_wrong
```
(Faz 2: bilinen püf noktasının kalan süresi `known_minutes`; bilinen öğle arası pencere içinde gelinirse `min(pencere sonu − varış, lunch_wait_max)` eklenir.)

**Ortak rastgele sayılar (CRN):**
- Her (gün, adres) için `u_stop`, `u_cause`, `u_learn`, `u_note`, `u_comply` çekilir.
- Her (gün, gönderi) için `u_ship` çekilir.
- Hepsi `np.random.default_rng([seed, gün, AKIŞ_KİMLİĞİ])` ile gün başında tek dizi olarak, talep sırasına göre üretilir. Talep sırası tüm kollarda aynıdır, dolayısıyla aynı adres tüm kollarda aynı sayıları alır.

### Tanıdıklık ve öğrenme (`familiarity.py`)

- **Ziyaret günü:** `f ← f + α·(1 − f)` (varsayılan α = 0,35; 3 ziyarette ≈ 0,73).
- **Ziyaret olmayan gün:** `f ← f · 2^(−1/H)` (yarı ömür H = 40 iş günü).
- **Yabancı blok** (metrik için): f < 0,2.
- **Püf noktasıyla karşılaşma:** Karşılaşma = püf noktası aktif ve etkisi gerçekleşti (başarısızlık ya da gecikme). `u_learn < p_learn` ise `known_quirks[(address, q)] = q.version` olur.
- **Not üretimi:** Karşılaşmada `u_note < note_propensity_c` ise not üretilir.

### Hafıza (kol D, `policies/memory_oracle.py`)

Bu, LLM ajanı gelmeden önceki deterministik yer tutucudur.

**`ingest`:** Her not `u_parse < memory.parse_accuracy` ise doğru (adres, püf türü) kaydına dönüşür. Değilse eşit olasılıkla üç şeyden biri olur:
- komşu adrese bağlanır
- yanlış püf türüne bağlanır
- düşer

Kişisel veri tuzaklı notlarda kişisel veri kaydedilmez. Kaydedilseydi bu bir "KVKK ihlali" metriği olarak sayılırdı; deterministik politika her zaman ayıklar.

**Kayıt alanları:** `adres, tür, ilk_gün, son_teyit, kaynak_sayısı, güven, süreli_mi, ttl`.
- Güven, kaynak sayısı ve tazelikle artar.
- Süreli türler TTL dolunca düşer.

**`hints_for`:** Rotadaki her durak için güveni ≥ `memory.min_confidence` olan kayıtlar ipucu olur. Kayıt mevcut püf sürümüyle uyuşuyorsa ve `u_comply < compliance` ise ceza kalkar. Uyuşmuyorsa (bayat kayıt) `δ_wrong` uygulanır.

**Geri bildirim** (`memory.feedback`, P1): İpucu verilen durakta kurye püf noktasının değiştiğini görürse kayıt `p_feedback` olasılıkla geçersiz kılınır.

**Hafızanın başlangıcı:** `memory.seed_from_warmup: true` (varsayılan) ile hafıza ısınma döneminden, yani sabit bölge döneminden not toplamaya başlar.
- **Önerilen yayılım sırası:** Önce hafıza sabit bölgedeyken toplanır, sonra dinamik planlamaya geçilir. Sunumda bu bir yol haritası maddesidir.
- **Duyarlılık analizi:** `false` ile hafızanın sıfırdan büyüme eğrisi ayrıca gösterilir.

### Notlar (`notes.py`)

Notlar kalıp tabanlı Türkçe üretilir. Her püf türü için 4–8 kalıp vardır, örnekler:

| Tür | Örnek kalıplar |
|---|---|
| `back_entry` | "giriş arka sokaktan ön kapı kilitli", "arka taraftan gir ön kapı açılmıyo" |
| `saturday_closed` | "cmt kapalı boşuna gelmeyin", "cumartesi burası kapalı" |
| `lunch_break` | "12 ile 1.5 arası kimse yok öğle arası" |
| `safety` | "güvenlikte kimlik bırakıyosun 5 dk sürüyo" |
| `bell` | "zil bozuk telefonla aramak lazım" |
| `position_wrong` | "harita yanlış gösteriyo bina 100m ileride benzinliğin arkası" |
| `reception` | "hepsi resepsiyona bırakılıyo" |

**Çeşitlendirme:** ünlü düşürme ve "-yo" ekleri, "abi" gibi dolgu sözcükler, alakasız cümle ("trafik berbattı bugün").

**Zorluk payları** (`notes.difficulty_mix`):

| Zorluk | Pay | Örnek |
|---|---|---|
| Kişisel veri tuzağı | %8 | "Ayşe hanım çok huysuz", "yaşlı teyze kapıyı geç açıyo", "0555 000 00 00 arayın". Telefon numaraları açıkça sahte kalıptadır. |
| Belirsiz adres | %8 | Barkodsuz, "şu köşedeki bina" |
| Yanlış bilgi | %5 | Not başka bir püf türünü anlatır |
| Bayat bilgi | — | Püf noktası değiştikten sonra eski sürümü anlatan not |

**Not alanları:** `id, gün, saat, kurye, gps (σ=25 m gürültü), barkod (opsiyonel), metin`.

**Gizli karşılık:** `notes_truth.json` içinde tutulur: `not_id → adres, püf_id, sürüm, kişisel_veri: bool, zorluk`.

### Senaryolar (`scenarios.py`)

Senaryolar yapılandırma üzerine YAML katmanlarıdır (`sim/config/scenarios/*.yaml`) ve birleştirilebilir:
- `normal`
- `leave_wave`
- `turnover`
- `borrowed_courier`
- `volume_shock`

**Kritik gün ve kurye seçimi:** Faz 2'den beri `critical_moment`: D kolunda çalışan yeni/ödünç/yedek kuryeler arasında hikaye önceliği ("kim gitsin" seçiminin yapıldığı gün > ödünç > yeni > yedek), sonra ipucu × yabancılık. Aday yoksa (D − C) farkının en büyük olduğu gün. (Faz 1'de: (D − B) farkının en büyük olduğu gün; o gün yabancı durak payı en yüksek ve ipucu en çok alan kurye.)

### Metrikler ve çıktılar (`metrics.py`, `run.py`)

```
runs/<run_id>/
  config.yaml            kullanılan tam yapılandırma
  meta.json              seed, paket sürümü, süre, senaryolar
  summary.json           kol × metrik (değerlendirme dönemi toplamı/ortalaması)
  daily.json             kol × gün × metrik
  learning_curve.json    yeni/ödünç kurye ilk 10 gün
  recovery.json          tahminci doğrulaması
  harvest.json           kol D günlük hasat istatistiği (Faz 2)
  snapshots/<kol>/<gün>.json   arayüz için harita verisi
  notes.json             gözlemlenebilir notlar (Hafıza Ajanı girdisi)
  notes_truth.json       notların gizli karşılığı (değerlendirme)
  truth.json             gizli gerçek özeti (yalnız değerlendirme ve "gerçek değer" paneli)
  report.md              okunabilir özet
```

**Snapshot şeması:**
```json
{ "app_data": true, "run_id": "...", "arm": "D", "day": 27, "weekday": 5, "depot": [39.0, 35.0],
  "routes": [{ "cluster": 3, "courier": "K07", "courier_kind": "new", "km": 41.2, "minutes": 472,
               "stops": [{ "id": "S1234", "lat": 39.01, "lng": 35.02, "n": 2, "eta": "10:42",
                           "ok": 2, "fail": 0, "reason": null, "hint": true, "unfamiliar": true }] }],
  "blocks": "blocks.json referansı" }
```

**Sağlamlık taraması:** `python -m cm_sim.sweep --grid sim/config/sweep.yaml --seeds 3 --workers 8` komutu `runs/sweep_<id>/` altına şunları yazar:
- `grid.json`: her kombinasyon için kol sıralaması ve fark
- `robustness.md`: manşet `headline` (Faz 2): D − A ilk denemede teslim farkı (min … max, medyan, ±0,15 içinde kalma payı, ≥ 0 payı, seed yayılımı), kurye-gün farkı (%), D − C farkı (min … max, pozitif payı). "D ≥ C ≥ B" oranı yalnız geriye uyumluluk için tutulur; manşet değildir (B rastgele atama)
- `sweep.json → manset`: aynı rakamlar, arayüz ve sunum için

**Öğrenme ve ablasyon çıktıları:** `python -m cm_sim.learning --seeds 12` → `runs/learning/learning.json` (`series.{C,D,D_memoryless}[{day, preventable_100, alt, top}]`, `first_week`, `first_week_paired_diff_C_minus_D`, `mastery_day`); `python -m cm_sim.ablation --seeds 3` → `runs/ablation/ablation.json`. `publish` ikisini `data/demo_run/` altına kopyalar.

## Varsayılan parametreler (özet)

Tamamı `sim/config/default.yaml` içinde, gerekçe yorumlarıyla.

| Alan | Varsayılan | Gerekçe |
|---|---|---|
| `days.warmup` / `days.eval` | 20 / 20 iş günü (Pzt–Cmt) | Isınmada tanıdıklık oturur; değerlendirmede ~3 cumartesi olur |
| `world.block_m` | 300 | "Sokak bilgisi" ölçeği |
| `world.addresses` | 6.000 | Günde ~1.500 durak üretir |
| `couriers.senior` / `couriers.reserve` | 20 / 2 | Orta büyüklükte bir kentsel şube |
| `couriers.skill_sigma` | 0,25 (lognormal, [0,6, 1,6] kırpma) | Ilımlı farklılık |
| `couriers.speed_sigma` | 0,12 ([0,8, 1,3]) | |
| `couriers.note_propensity` | Beta(2, 5), ort. ≈ 0,29 | Temkinli: karşılaşmaların çoğu nota dönüşmez |
| `outcome.p0` | ev 0,04 · apartman 0,03 · site 0,02 · iş yeri 0,01 · toplu 0,002 | Bilgiden bağımsız taban |
| `outcome.eta_nav` / `outcome.nav_min` | 1,0 / 1,5 dk | Yabancı blokta taban oran 2 kat, +1,5 dk |
| `quirks.prevalence` | site 0,40 · iş yeri 0,35 · apartman 0,12 · ev 0,08 · toplu 1,0 | |
| `quirks.effects` (δ_fail / τ dk) | back_entry 0,10/4 · saturday_closed 0,90/0 (Cmt) · lunch_break 0,80/0 (12:00–13:30) · guvenlik 0,03/6 · zil 0,20/2 · position_wrong 0,25/5 · resepsiyon 0,05/5 | |
| `quirks.change_rate` / `quirks.temporary_rate` | 0,10 / 0,02 | Bayat bilgi üretmek için |
| `learning.p_learn` / `familiarity.alpha` / `familiarity.half_life` | 0,7 / 0,35 / 40 | |
| `memory.parse_accuracy` | 0,85 | Hafıza Ajanı ölçülünce güncellenir |
| `memory.compliance` / `outcome.delta_wrong` | 0,9 / 0,05 (+3 dk) | |
| `planning.target_minutes` / `planning.band` | 460 / [378, 528] | |
| `assignment.w_fail` / `assignment.w_time` | 1,0 / 1/20 | 20 dk ≈ bir başarısız teslim |
| `routing.enabled` / `defer_closed` / `window_repair` / `service_correction` | true | Hafıza-farkında plan ve rota (kol D); kapalıysa D = Faz 1'deki yalnız kapı ipucu |
| `routing.defer_min_sources` | 2 | Planda erteleme için en az 2 bağımsız kaynak (VARSAYIM) |
| `routing.extra_service_min` | back_entry 1 · guvenlik 2 · resepsiyon 1 · roadwork 2 | Planlayıcının servis süresi varsayımı (VARSAYIM) |
| `routing.time_scale` / `routing.window_margin_min` | 1,1 / 10 dk | Beklenen varış ölçeği; pencere güvenlik payı (VARSAYIM) |
| `quirks.lunch_wait_max` | 15 dk | Öğle arasını bilen kurye pencerede gelirse ek bekleme tavanı (VARSAYIM) |
| `quirks.effects.*.known_minutes` | güvenlik 2 · resepsiyon 1 · arka giriş 1 · yol çalışması 2 dk | Bilinse de kalan ek süre (VARSAYIM) |
| `memory.harvest_per_day` / `harvest_per_senior` / `p_answer` | 30 / 3 / 0,8 | Proaktif hasat (VARSAYIM) |

## Hata yönetimi

- **Yapılandırma:** pydantic doğrulaması alan yolu ve sebebiyle hata verir.
- **Planlama:** Müsait kurye sayısı sıfır olan gün kayda geçer, o gün atlanır, metriklerde işaretlenir.
- **Politika hatası:** Bir politika geçersiz eşleme döndürürse (aynı kurye iki kümeye ya da var olmayan kurye) simülasyon politika adıyla birlikte hata verir. Sessizce düzeltilmez.

## Teslim zamanı (Faz 2b)

- **Dünya (`world.py`, `config.py`, `default.yaml → presence`):** profil başına hafta içi / Cumartesi saat dizileri; `mix[adres türü]` ile profil seçimi; `intensity_sigma` lognormal adres çarpanı; `S_PRESENCE=5` ayrı RNG akışı. `world.p_absent(adres, varış dk, gün tipi)`; yokluk durak düzeyinde tek çekilişle belirlenir (CRN). `presence.enabled=false` → eski `outcome.p0` modeli.
- **`delivery_time.py` (saf):** `SLOT_NAMES`, `BORDERS=(720, 840, 960, 1080)`, `slot(mins)`, `day_type`, `TimeRecord.add(...)` (`att`, `abs`: (n_adres, 2, 5)), `counts_from_log(..., before_day)`, `Params.from_dict(cfg.time_analysis)`, `time_findings(...)`, `address_finding`, `fits_route`, `proposal_text`. Tür şekli `q[tür, dilim]`; adres genel oranı `p̄ = (abs + κa·q̄)/(att + κa)`; dilim tahmini `p[d] = (abs_d + κs·m_d)/(att_d + κs)`, `m_d = p̄·q[d]/q̄`. Güven Beta nicelik integraliyle.
- **`routing_memory.py`:** `StopRule.presence` (dilim başına tahmini bulunamama), `repair_times` (aday = bulgu düğümünün tüm or-opt yerleri + onu içeren tüm 2-opt ters çevirmeleri; en iyi aday maliyeti ≥ `time_min_gain_min` düşürüyor ve pencere ihlalini artırmıyorsa uygulanır), `expected_time_fails`; değişiklik kaydı `{type: "time", move: move|reverse, old_order, new_order, ...}`. `agents/route.py` Faz 2 metin hatası ("37. sıradan 35. sıraya", gerçek 36→34) düzeltildi.
- **Motor kol D:** bulgular `History.time`'dan (yalnız geçmiş günler); `no_time` karşı-olgu aynı CRN ile; `time_stats`; doğruluk = gizli gerçek bulunamama farkı ≥ 0,10 olan bulgu payı.
- **Dışa aktarım:** `delivery_log.json`, `time.json`, `truth.presence`, `summary.time_analysis`, `meta.time_example` (seçim: zaman onarımının taşıdığı, zamansızda `recipient_absent` / zaman-farkında teslim, ≥ 6 geçmiş deneme, demo gününe en yakın), snapshot `counterfactual.no_time` + `time_stops`, `plan.time_fail`.
- **Ablasyon:** `no_time`, `full_g60`, `no_time_g60`, `time_contribution`.
- Test: `sim/tests/test_delivery_time.py` (7 hızlı); kalibrasyon 14/14.

## Onarım rotayı uzatmaz (Faz 2c)

- **Kısıt:** `RepairLimits` (`max_extra_min`, `max_extra_km`, `band_max`, `shift_end`); `plan_route(..., limits=)` hem pencere hem zaman onarımında her adayı onarım öncesi rotayla karşılaştırır. Beklenen süre = sürüş + servis + bilinen öğle beklemesi (`min(pencere sonu − varış, quirks.lunch_wait_max)`, planlanan dk). Kısıtı bozan aday maliyetine bakılmadan elenir; servis düzeltmesi sırayı değiştirmez.
- **`time_blocked`:** onarımdan sonra en iyi dilimden ≥ `time_blocked_diff` kötü dilimde kalan bulgu; `reason` + `min_extra_min`.
- **`time_alternatives(routes, ...)`** (`routing_memory.py`, saf): aynı rota nedeni → aktarma (başka kuryenin rotasına, iki rotada birlikte kısıt; kabul edilen sonrakilerde hesaba katılır) → ertesi gün / akşam teslim noktası; her biri `sms_text` taşır. Motor kol D bunu hesaplar ve yalnız raporlar, uygulamaz (karşı-olgu ve ölçülen etki değişmez). Metinler `delivery_time.alternative_text`, `REASON_TEXT`, `OPTION_NAME`.
- **Dışa aktarım:** `summary.time_analysis.{constraint, overtime_route, alternatives}`, `counterfactual_daily.*.planned_min`, `time.json → alternatifler`, snapshot `plan.limits` / `plan.time_blocked`, `meta.time_example` (seçimde kısıt şartı) + `meta.time_example_constraint`, arm `route_minutes_per_day`.
- **Ablasyon:** `full_tol5`, `no_time_tol5`, `unconstrained`, `no_time_unconstrained`; `time_contribution` yeni sütunlar (`route_min_D`, `ayni_rota_*`).
- Test: `sim/tests/test_repair_limits.py` (7 hızlı).

## Test stratejisi

| Test | Ne doğrular |
|---|---|
| Determinizm | Aynı yapılandırma + seed ile `summary.json` bayt düzeyinde eşit |
| CRN | Aynı (gün, adres) için çekilen sayılar tüm kollarda aynı |
| Bilgi etkisi kapalı invaryantı | `skill_sigma = 0`, `eta_nav = 0`, tüm `δ = 0`, `nav_min = 0` iken B, C, D kollarının teslim sonuçları birebir aynı. Bu, CRN ve politika izolasyonunun birlikte çalıştığının kanıtı. |
| Gizlilik | Politika çağrısına giden argümanlar özyinelemeli gezilir; `Courier`, `Address`, `Quirk`, `Block` örneği bulunursa test başarısız |
| Monotonluk (istatistiksel, 3 seed) | `parse_accuracy` 0,5 → 0,95 arttığında D'nin ilk denemede teslim oranı azalmaz (tolerans 0,2 puan) |
| Tahminci | Varsayılanda Spearman(ρ̂, gerçek beceri) > Spearman(naif, gerçek beceri) |
| Planlama | Dinamik kümelerde planlanan süre CV'si varsayılanda < 0,15. Her durak tam bir kümede. |
| Hafıza-farkında rota (Faz 2) | `sim/tests/test_anchored.py` (yeniden yazıldı): D kendi planını kurar, planda erteleme ≥ 2 kaynak, pencere onarımı, karşı-olgu aynı rastgele sayılarla; `test_privacy.py` hasat yolunu da kapsar |
| Hız (`@pytest.mark.slow`) | Varsayılan çalıştırma < 60 sn |
| Yasaklı içerik | Aşağıdaki kalıplar `.kiro/`, `.venv/`, `runs/` ve testin kendisi dışında hiçbir metin dosyasında geçmez |

**Yasaklı kalıplar (`sim/tests/test_forbidden_content.py`):**
- `\bARP\b`, `\bCrowd\b`, `CrowdDB`, `ArpSchedule`, `ExternalCluster`, `ExternalRoute`
- `araskargo\.com\.tr`, `map-cls`
- `\b6678\b`, `\bBKZ\d{2}\b`

Test kalıpları kaynak kodda parçalanmış dizgilerle kurulur (ör. `"AR" + "P"`). Böylece testin kendisi taramaya takılmaz.

## Ajanlara köprü (sonraki spec'ler)

- **Atama Ajanı:** `AssignmentPolicy`'yi uygular. Araçları:
  - `estimation.expected_cost`
  - `solve_assignment` (Hungarian)
  - `what_if` (ör. "kurye X yokmuş gibi yeniden çöz")
  - `explain_cluster` (yabancı durak sayısı, hafıza kapsamı)
  Simülatördeki C kolu ile aynı hesabı kullanır.
- **Hafıza Ajanı:** `MemoryPolicy.ingest`'i uygular. `notes.json` + `notes_truth.json` ile doğruluğu ölçülür: adres eşleme, tür, kişisel veri ayıklama, bayat bilgi. Ölçülen doğruluk `memory.parse_accuracy`'ye yazılır ve D kolu bu değerle yeniden koşulur. Sunumdaki cümle: "Ajanın ölçülen doğruluğuyla simülasyon."
- **Brifing Ajanı:** `MemoryPolicy.hints_for` çıktısını ve snapshot'taki rotayı alır; sabah brifingini ve kapı cümlelerini üretir.
