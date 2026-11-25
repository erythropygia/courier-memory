# Gereksinimler: Orkestratör Ajanı (günün ajanı + insan onayı)

## Giriş

Orkestratör, şubenin sabahını uçtan uca yöneten araç kullanan ajandır: hacmi okur, yoğunluğu ve kapasite açığını görür, açık varsa komşu şubeden kurye ister ("kim gitsin"), çekirdek bölgeli atamayı kurdurur, riskli rotaları kontrol eder ve müdüre gerekçeli öneri sunar. Müdür onaylar, reddeder ya da düzenler; plan ancak o zaman kesinleşir.

İlke (`tech.md`): **karar LLM'de, hesap araçta.** Kapasite, aday sıralama, Hungarian atama, küme dağıtımı, ETA ve rota deterministik Python araçlarıdır. Mock modunda kurallı yedek aynı araçları aynı sırayla çağırır ve aynı iz biçimini üretir; Bedrock bağlanınca arayüz değişmez.

Veri: yalnız çalıştırma klasörü (`data/demo_run/`, `docs/sozlesmeler.md` §1) ve canlı hafıza (`MemoryBook`). Sözleşme: `docs/sozlesmeler.md` §3, §4, §5.

## Gereksinimler

### Gereksinim 1: Deterministik araçlar (`DayTools`)
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanın söylediği her sayının bir hesaptan geldiğini bilmek istiyorum.

#### Kabul kriterleri
1. `read_volume`: günün gönderi, durak, küme sayısı; olağan gönderi = aynı haftagünündeki diğer değerlendirme günlerinin medyanı; `volume_diff`; `density` ∈ `yogun | olagan | dusuk` (eşik ±%15).
2. `capacity_gap`: `required_courier_day` = küme sayısı; `local_available` = ödünç olmayan müsait kurye; `shortfall`, `extra`; yerel kadroyla atanamayan `open_clusters`; `shortfall_unclosed` (bant üstü dk, bandı aşan kurye, beklenen başarısız).
3. `neighbor_candidates(need, exclude, current_borrowed)`: komşu şube aday havuzu = o gün müsait `borrowed` türü kuryeler. Her aday için yerel kadro (+ mevcut ödünçler) + aday ile plan kurulur; adayın alacağı kümede `familiar_share`, `memory_coverage`, `expected_fails`, `expected_min`, `within_band`, planın `plan_cost` ve `days_worked_in_branch` raporlanır. Sıra plan maliyetine göredir; `proposed` açgözlü seçimle en fazla `need` kadardır; adaylar eşitse `tie: true` ve gerekçe bunu söyler.
   - **Demo gününde eşitlik çıkmaz.** Adaylar bu şubenin ortak sınır sokaklarını komşu şubeden dağıtma geçmişine göre (`calendar.borrowed[].border_side/border_depth_km`) farklı tanıdık paya sahiptir: gün 32'de alacağı kümede tanıdık durak: Onur %100 > Gökhan %64 > Melis %0. Plan maliyeti 0,1'e yuvarlanınca eşit çıkan adaylarda sıra beklenen başarısızlığa göredir (kalite önce) ve gerekçe eşitliği adıyla yazar. Sıralama performansa değil gözlemlenebilir bölge tanıklığına dayanır ("sınır sokak tanıklığı"). Eşitlik dalı yine de korunur (tüm adaylar yabancıysa).
4. `core_assignment(borrowed, exclude, pin)`: havuz = yerel − hariç + ödünç; Hungarian (atama matrisinin `cost` alanı). Kurye küme sayısından azsa atanamayan küme en yakın 2 kümeye eşit bölünür (`distributed_clusters`, `dispatch_note`). Çıktı: satırlar, `total` (`courier_count, expected_fails, unfamiliar_stop, memory_unfamiliar, over_band_courier, over_band_min, expected_min_total, cost`), `own_zone_share`, `idle_couriers`, `eta_model`. Yerel kurye `borrowed` olarak verilirse `ValueError`.
5. `compute_route(cluster_id, courier_id)`: `RoutePlanner.plan` çıktısı; `constraints`, `changes`, `constraint_source` alanları her zaman vardır. `MemoryConstraints` ile **hafızalı rota**: `cm_sim.routing_memory` fonksiyonlarıyla planda erteleme (≥ 2 kaynak), servis süresi düzeltmesi ve pencere onarımı uygulanır; çıktı `comparison` (`memoryless` ↔ `memory` sıra, `diff`, simülasyon karşı-olgusu) ve `same_as_sim` taşır. Canlı hafıza simülasyonun o günkü hafızasıyken ajanın sırası kol D'nin yürüttüğü sırayla birebir aynıdır (408/408 rota, test); not ya da hasat cevabı hafızayı değiştirince `same_as_sim: false` ve rota değişir. Çıktı biçimi: `docs/sozlesmeler.md` §6.
6. Beklenen süre (`expected_min`) `EtaModel` ile hesaplanır: `a × planlanan + b × (exp_min − taban servis)`; katsayılar yalnız o günden **önceki** değerlendirme günlerinin gerçekleşen rota sürelerine oturtulur (30 rotadan azsa a=1, b=0,5).
7. Aynı girdi her zaman aynı çıktıyı verir.
8. **Orkestratör planı = simülatör planı:** onaylanan plan, simülatör D planıyla aynı kuryeleri seçer (aksi halde brifing tutarsızlaşır; hasat atama matrisini yeniden hesaplamadığı için bu eşitlik korunur). `EtaModel` bilinen püf noktası süresini de içerir: demo günü beklenen başarısız 143,2, kendi bölgesinde %92, bant üstü 14 kurye / 654 dk.
9. **Teslim zamanı:** iki yeni araç. `delivery_time_analysis {min_confidence}`: geçmiş kayıtlardan (yalnız o günden önceki günler) adres bulguları (`window`, `confirmation`), `fits_route` sayısı, `bulgular[≤25]`, `teyitler[≤10]`, `rule_policy`. `apply_time_constraint {min_confidence, exclude[], rationale}`: hangi bulguların plana gireceğini seçer (`{min_confidence, excluded, applied, cluster_count, rationale}`); LLM karar verir, sayı ve seçim araçtadır. Sıra: `core_assignment` → `delivery_time_analysis` → `apply_time_constraint` → `compute_route`. Mock kurallı yedek (`routing.time_min_confidence`) aynı araçları aynı sırayla çağırır, aynı iz biçimini yazar. `proposal`/`plan` `time_constraints{min_confidence, excluded, applied} | null` taşır.
10. **Zaman onarımlı rota:** `compute_route` `RoutePlanner(time="auto")` ile `routing_memory.plan_route(time_repair=)` çağırır: `constraints[].kind = "time_preference"`, `changes[].type = "time"` (1 tabanlı sıra), `comparison.no_time`, `diff.time_carried`, `diff.expected_absence`, `time_findings[]`. Ajan rotası simülatör rotasıyla birebir aynıdır (408/408 rota, `same_as_sim`).
11. **Onarım rotayı uzatmaz:** `compute_route` aynı sert kısıtla çalışır (`routing_memory.RepairLimits`): onarım beklenen rota süresini, km'yi (tolerans), vardiya bandını ve vardiya bitişini kötüleştiremez; çıktı `time_unshiftable[]`, `comparison.route_constraint`, `diff.time_unshiftable` taşır. Kısıt kuralı iz'de bir "karar" cümlesiyle söylenir.
12. **Kaydırılamayan bulgunun alternatifleri:** yeni araç `time_alternatives` (girdi yok): kısıt yüzünden aynı rotada kaydırılamayan duraklar için aktarma / ertesi gün / akşam teslim noktası + alıcıya SMS önerisi (`RoutePlanner.day_alternatives`; simülatör kol D ile aynı `cm_sim.routing_memory.time_alternatives`). Sıra: `core_assignment` → `delivery_time_analysis` → `apply_time_constraint` → `time_alternatives` → `compute_route`. Mock kurallı yedek aynı araçları aynı sırayla, aynı iz biçimiyle çağırır. Öneri `time_alternatives` (ilk 10: adres, etiket, kurye, secenek, neden, target_courier, metin, sms_text) taşır; riskler "… durak kısıt yüzünden aynı rotada kaydırılamadı; alternatif öneriler … onayınızı bekliyor" der. Karar müdürdedir; alternatif otomatik uygulanmaz. İstem `prompts/orchestrator.md` güncel.

### Gereksinim 2: Ajan akışı ve iz
**Kullanıcı hikayesi:** Bir yönetici olarak, ajanın adım adım ne yaptığını (araç → sonuç → karar) canlı görmek istiyorum.

#### Kabul kriterleri
1. `Orkestrator.plan(gün, iz)` önerilen sırayla çalışır: `read_volume → capacity_gap → (açık varsa) neighbor_candidates → core_assignment → (ödünç/yeni kuryeler için en çok 3) compute_route → present_proposal`.
2. Canlı yolda `LLM.run_agent(..., on_text=...)` modelin her metin bloğunu `decision` olayı olarak, araç sarmalayıcıları `tool` ve `result` olaylarını yazar. Bitiş aracı `present_proposal` yalnız `borrowed / exclude / pin / rationale / risks / questions` taşır; plan araçta yeniden hesaplanır (LLM sayı yazmaz).
3. Mock yolunda kurallı yedek aynı araçları aynı sırayla çağırır, `decision` metinlerini şablondan üretir; olay biçimi aynıdır, yalnız `source` farklıdır (`llm | kural | insan`).
4. Canlı/replay yolu hata verirse `fallback` olayı yazılır, kurallı yedek devam eder, sonuçta `degraded: true` ve `error` döner.
5. Mock iz deterministiktir (saat damgası yok): aynı gün iki kez çalıştırılınca bayt bayt aynı iz.
6. Planlama evresi `proposal` ve `awaiting_approval` olaylarıyla biter.
7. Yoğun günde (demo günü) ödünç kurye sayısı açığa eşittir ve boşta kurye kalmaz.

### Gereksinim 3: Senaryo sorusu
**Kullanıcı hikayesi:** Bir şube müdürü olarak, "X gelmezse?" sorusuna sayılarla iki seçenek görmek istiyorum.

#### Kabul kriterleri
1. `Orchestrator.ask(gün, soru, oneri, iz)` aynı izi sürdürür (`start{task: ask}` … `tool:respond` → `response`).
2. "X gelmezse" (bir ya da birden çok isim): (1) komşu şubeden yerine aday (`neighbor_candidates` + `core_assignment`) ve (2) kimse gelmez, kümeler dağıtılır (`core_assignment`). Her seçenek için `total` ve öneriye göre `diff`; skor = planlayıcı ağırlıklarıyla `w_fail × expected_fails + w_time × over_band_min`.
3. "X yerine Y": X hariç, Y X'in kümesine sabitlenir.
4. Yanıt `{response, new_proposal|null, diff|null, alternatives[], mode, degraded, trace[]}`.

### Gereksinim 4: İnsan onayı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, son kararı ben vermek ve öneriyi düzeltebilmek istiyorum.

#### Kabul kriterleri
1. `decision` ∈ `onay | ret | duzenle`. `approval`: öneri plan olur. `ret`: plan yok. `edit`: verilen `[{cluster, courier}]` `evaluate_plan` ile doğrulanır (kurye havuzda olmalı, küme ve kurye tekrarı yok), aynı ölçülerle değerlendirilir, gerekçeye "Müdür düzenledi" eklenir.
2. Karar sonrası iz'e `human_decision` ve `done` (kaynak `human`) yazılır; kesinleşen plan `SessionStore.planlar[gün]`'e konur.
3. Onay beklemeyen koşuya ikinci karar ya da senaryo sorusu verilemez (`ValueError` → API 400/409).

### Gereksinim 6: Temassız zincir, acil durumda müdür
**Kullanıcı hikayesi:** Bir şube müdürü olarak, olağan günde zincirin bana dokunmadan çalışmasını; yalnız gerçekten acil durumda devreye girmeyi istiyorum.

#### Kabul kriterleri
1. WHEN gerekçeli plan hazır olduğunda THE SYSTEM SHALL deterministik acil durum denetimi yapmalıdır (`Orchestrator.escalation`); karar LLM'de değildir.
2. WHEN acil durum yoksa THE SYSTEM SHALL planı müdüre göndermeden kesinleştirmeli, iz'e `auto_decision` ve `done{finalized}` yazmalı (kaynak `rule`) ve planı `SessionStore.plans[gün]`'e koymalıdır.
3. WHEN kapasite açığı komşu şubeden gelenlerle kapanmıyorsa (`capacity`), tek kuryede bant üstü ≥ 240 dk ya da şube toplamı ≥ 1500 dk ise (`overtime`), plan geçmişe bakmayan atamadan kötüyse (`plan_worse`) ya da müdür acil durum bildirdiyse (`manager_review`, `manual`) THE SYSTEM SHALL iz'e `escalation{reasons}` ve `awaiting_approval` yazmalı ve müdür kararını beklemelidir (Gereksinim 4).
4. WHEN canlı yol ve kurallı yedek planı çıkaramazsa THE SYSTEM SHALL `escalation{agent_failed}` ve `done{error}` yazmalıdır.
5. WHEN koşu temassız kesinleştiyse THE SYSTEM SHALL karar ve senaryo sorusunu reddetmelidir (Gereksinim 4.3).

### Gereksinim 5: API ve akış
#### Kabul kriterleri
1. `POST /api/orchestrator/start {day, manager_review?}` arka planda koşar; `GET /api/orchestrator/session/{id}?after=n` (poll) ve `GET /api/orchestrator/session/{id}/stream?after=&tempo_ms=` (SSE, `event: <type>`, `data: <event>`; planlama bitince `event: last`).
2. `POST /api/orchestrator/plan {day}` eşzamanlı aynı sonucu döndürür.
3. `POST /api/orchestrator/session/{id}/decision {decision, assignment?, note?}`, `POST /api/orchestrator/session/{id}/ask {question, history?}`, `GET /api/plan/{day}` (yoksa 404).
4. Koşular bellek içindedir; sunucu yeniden başlarsa kaybolur.
