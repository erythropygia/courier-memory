# Uygulama planı: Dünya ve simülatör

Sıra bilinçlidir. 6. görevin sonunda A ile B kollarını karşılaştıran uçtan uca çalışan bir dilim olur, sonra katman katman zenginleşir. Her görev kendi testleriyle biter.

- [x] 1. Proje iskeleti ve yapılandırma
  - `pyproject.toml` (Python 3.12; numpy, scipy, pydantic>=2, pyyaml; dev: pytest), `sim/cm_sim/` paketi, `sim/tests/` (`.gitignore` hazır: `runs/` ve `.venv/` dışarıda; `cassettes/` repoda kalır)
  - `config.py`: pydantic modeli; `sim/config/default.yaml` tüm alanlar ve gerekçe yorumlarıyla
  - `--set a.b=c` ezme desteği; geçersiz alan için yol + sebep içeren hata
  - `rng.py`: `day_streams(seed, day, n)` ile CRN akışları
  - _Gereksinimler: 1.1, 1.2, 1.5, 7.4_

- [x] 2. Yasaklı içerik koruması
  - `sim/tests/test_forbidden_content.py`: tasarımdaki kalıplar, parçalanmış dizgilerle; dışlamalar; dosya:satır raporu
  - _Gereksinimler: 14.1, 14.2_

- [x] 3. Coğrafya, bloklar, adresler ve püf noktaları
  - `world.py`: blok ızgarası, halka + gürültü ile tür ataması, blok zorluğu, adres üretimi (blok içinde), adres türü
  - Püf noktası ataması, türe göre etkiler; kalıcı/süreli; değişim takvimi (sürüm artışı)
  - `blocks.json` dışa aktarımı (arayüz için)
  - Testler: adresler blok sınırı içinde; tür oranları yapılandırmaya ±%5 yakın; aynı seed aynı dünya
  - _Gereksinimler: 2.1–2.5, 3.1–3.4_

- [x] 4. Kuryeler ve talep
  - `couriers.py`: gizli özellikler (kırpılmış lognormal/Beta), türler, takvim
  - `demand.py`: Poisson talep, haftanın günü çarpanı, şok günleri; talep sırası deterministik
  - Testler: beceri aralığı; talep kollardan bağımsız (aynı seed aynı talep)
  - _Gereksinimler: 4.1–4.4, 5.1–5.4_

- [x] 5. Planlama
  - `planning.py`: dengeli k-means (pişmanlık sıralı kapasiteli atama), onarım, en yakın komşu + vektörize 2-opt, planlanan süre, ETA
  - Sabit bölgeler (ısınma ortalamasından), yokluk kuralı (`reserve` / `split`)
  - Testler: her durak tam bir kümede; küme sayısı ≤ müsait kurye; dinamik kümelerde süre CV'si < 0,15
  - _Gereksinimler: 6.1–6.5_

- [x] 6. Sonuç modeli, tanıdıklık ve ilk uçtan uca dilim (A ve B)
  - `outcome.py`: durak düzeyi bilgi başarısızlığı + gönderi düzeyi alıcı yok; neden kodu; süre; zamana bağlı püf noktaları
  - `familiarity.py`: ziyaret artışı, yarı ömürlü azalma, püf öğrenme
  - `policies/base.py` (`AssignmentPolicy`, `MemoryPolicy`, `*View` tipleri, `HistoryReader`), `fixed_zone.py`, `blind.py`
  - `run.py`: ısınma → çatallama → kollar; ortak kümeler B/C/D için bir kez hesaplanır
  - `metrics.py` (ilk sürüm): ilk denemede teslim, neden dağılımı, km, araç-gün, bant, CV, yabancı durak payı; `summary.json`, `daily.json`, `report.md`
  - Testler: determinizm (bayt eşitliği); CRN; gizlilik (politikaya gizli nesne gitmiyor)
  - _Gereksinimler: 7.1–7.5, 8.1, 8.2, 8.5, 9.1, 9.2, 9.3 (A, B), 13.1, 13.3, 1.3, 1.4_

- [x] 7. Uyum tahmincisi ve kol C
  - `estimation.py`: blok oranı büzülmesi, kurye oranı (dolaylı standartlaştırma), hız tahmini, `expected_cost`, `report_recovery` (`recovery.json`)
  - `policies/fit_assign.py`: maliyet matrisi + `linear_sum_assignment`; dikdörtgen matris
  - Testler: Spearman(ρ̂) > Spearman(naif); geçersiz eşlemede politika adını içeren hata
  - _Gereksinimler: 9.3 (C), 9.4, 10.1–10.3_

- [x] 8. Notlar ve kol D (deterministik hafıza)
  - `notes.py`: kalıp tabanlı Türkçe notlar, çeşitlendirme, zorluk payları (kişisel veri / belirsiz / yanlış / bayat), GPS gürültüsü; `notes.json` + `notes_truth.json`
  - `policies/memory_oracle.py`: `ingest` (ayrıştırma doğruluğu parametreli), güven/TTL, `hints_for`, uyum ve bayat ipucu cezası; `seed_from_warmup`
  - Kol D için maliyette `m_s` (hafıza kapsamı); hafıza kapsamı metriği
  - Testler: bilgi etkisi kapalıyken B, C ve D eşit; `parse_accuracy` monotonluğu (3 seed)
  - _Gereksinimler: 8.3, 8.4, 9.3 (D), 9.4, 11.1–11.5, 13.1_

- [x] 9. Senaryolar ve kritik an seçimi
  - `sim/config/scenarios/*.yaml`: normal, leave_wave, turnover, borrowed_courier, volume_shock; katman birleştirme
  - Kritik gün / kurye seçimi → `meta.json`
  - Yeni/ödünç kurye öğrenme eğrisi → `learning_curve.json`
  - _Gereksinimler: 4.2, 4.3, 5.3, 12.1–12.3, 13.2_

- [x] 10. Arayüz için dışa aktarımlar
  - `snapshots/<kol>/<gün>.json` şeması (tasarımdaki gibi), her dosyada `"app_data": true`
  - Gizli gerçek dosyaları (`truth.json`, `notes_truth.json`) ayrı ve açıkça adlandırılmış
  - _Gereksinimler: 13.3, 14.3_

- [x] 11. Sağlamlık taraması
  - `cm_sim/sweep.py` + `sim/config/sweep.yaml`: parametre ızgarası × seed, `multiprocessing`
  - `grid.json`, `robustness.md` (`headline` = D − A ve D − C aralıkları; "D ≥ C ≥ B" oranı yalnız geriye uyumluluk)
  - _Gereksinimler: 13.4_

- [x] 12. Performans ve son kontrol
  - Profil; gerekirse 2-opt tur sınırı ve vektörizasyon; `@pytest.mark.slow` hız testi (< 60 sn)
  - `report.md` gözden geçirme: dil `sunum-dili.md`'ye uygun, "Uygulama verisi · 1 aylık geçmiş" etiketi, "tahmini parametrelerle" ifadesi
  - _Gereksinimler: 13.5_

- [x] 13. Kalibrasyon ve uzun dönem
  - `world.recurring_share/recurring_sigma`, `demand.sporadic_share`: iki adres havuzu; `planning.fixed_zone_slack` ve ek kurye taşması
  - `sim/config/calibration.yaml` + `cm_sim/calibration.py` (hedef ↔ uygulama verisi tablosu, `calibration.json`)
  - `scenarios/long_term.yaml`; `publish` uzun dönem özetini ve kalibrasyonu ekler
- [x] 14. Çekirdek bölgeli dinamik plan (C/D) ve mevcut yapının gerçekçiliği
  - `AnchoredPlanPolicy`, `HistoryReader.familiar_blocks`, `StopView.x/y`, `DayContext.block_xy`; C/D plan paylaşımı
  - `planning.fixed_zone_demand_drift`, `extra_courier_mode`; `in_band_planned_share`, `planned_cv`; kalibrasyon 14/14

- [x] 15. Hafıza-farkında plan ve rota (kol D)
  - `routing_memory.py`: `StopRule`, `rule_from_entries`, `plan_route`, `repair_windows`, `arrivals` (saf fonksiyonlar; planda erteleme ≥ 2 kaynak, servis düzeltmesi, pencere onarımı)
  - `engine.py`: D kendi planını kurar (C'yi kopyalamaz); `policies/simple.py` `extra_w`, `policies/memory_oracle.py` `rules_for`; `config.py` + `default.yaml` `routing` bölümü
  - Karşı-olgu: her D rotası hafızasız / yalnız ipucu / hafızalı aynı rastgele sayılarla yürütülür
  - Testler: `test_anchored.py` (yeniden), `test_privacy.py`; canlı ajan sırası ile kol D sırası birebir aynı (`agents/tests/test_memory_route.py`)
  - _Gereksinimler: 15.1–15.5_
- [x] 16. Öğle arası ve servis süresi düzeltmesi
  - `outcome.py`: bilinen öğle arası pencerede `min(pencere sonu − varış, lunch_wait_max)`; `quirks.effects.*.known_minutes`; `plan_deferred_result` ve `wrong_deferral` nedeni
  - Kapı hızı tahmini yalnız tanıdık duraklardan (`engine._execute`)
  - Kalibrasyon 14/14 korunur
  - _Gereksinimler: 7.1, 7.2, 7.6, 7.7_
- [x] 17. Hedef 2: ödünç kuryeler ve sınır tanıklığı
  - `couriers.py` çok dönemli ödünç; `calendar.borrowed[].border_side/border_depth_km`; ödünç/çekirdeksiz sırası `days_in_branch`
  - `borrowed_courier.yaml`: Onur doğu 2 km, Gökhan kuzey 1,2 km, Melis hiç; `critical_moment` "kim gitsin" önceliği
  - _Gereksinimler: 12.1, 12.3, 18.1–18.3_
- [x] 18. Hasat (kol D)
  - `memory_oracle.harvest`, `rng.S_HARVEST`, `history.addr_days`; `memory.harvest_per_day/harvest_per_senior/p_answer`; ayrılan kuryeye devir teslim soruları
  - `harvest.json` dışa aktarımı; atama matrisi hasattan önceki, anlık görüntü hafızası sonraki
  - _Gereksinimler: 16.1–16.5_
- [x] 19. Hedef 1 deneyi ve ablasyon
  - `learning.py` + `scenarios/hiring.yaml` (`python -m cm_sim.learning --seeds 12`)
  - `ablation.py` (`python -m cm_sim.ablation --seeds 3`; varyantlar `hint_only`, `hint_harvest`, `hint_route`, `full`)
  - _Gereksinimler: 15.6, 17.1–17.4_
- [x] 20. Dışa aktarım, sağlamlık manşeti, yayım
  - `export.py`: `plan`, `counterfactual`, `memory_routing`, `same_route`, `meta.critical.memory_gain`
  - `sweep.py`: `headline` (D − A, D − C aralıkları); `publish.py`: `learning.json`, `ablation.json`, `harvest.json`
  - Yeniden üretim sırası: `README.md` → "Rakamları yeniden üretme sırası"
  - _Gereksinimler: 13.4, 19.1–19.4_
- [x] 21. Teslim zamanı: saate bağlı "alıcı yok" ve zaman analizi
  - `presence` bölümü + `world.p_absent`, `rng.S_PRESENCE=5`; kalibrasyon 14/14 korunur
  - `cm_sim/delivery_time.py`: `TimeRecord`, `counts_from_log(before_day)`, Beta-Binomial büzme, `window` / `confirmation` bulguları, `time_analysis` parametreleri
  - `routing_memory.py`: `StopRule.presence`, `repair_times`, `plan_route(time_repair=)` → `time_fail`; 1 tabanlı sıra numaraları
  - `engine.py` kol D: `History.time`, `no_time` karşı-olgu, `time_stats`; `routing.time_min_confidence`
  - `export.py`: `delivery_log.json`, `time.json`, `truth.presence`, `summary.time_analysis`, `meta.time_example`, `counterfactual.no_time`, `plan.time_fail`
  - `ablation.py`: `no_time`, `full_g60`, `no_time_g60`, `time_contribution`; `publish.py` yeni dosyaları kopyalar
  - Test: `sim/tests/test_delivery_time.py` (7 hızlı); sim toplamı 24 hızlı + 4 yavaş
  - _Gereksinimler: 20.1–20.9_
- [x] 22. Onarım rotayı uzatmaz: sert kısıt ve kaydırılamayan bulgunun alternatifleri
  - `routing_memory.py`: `RepairLimits`, `plan_route(limits=)` (pencere + zaman onarımı kısıtlı), `time_blocked`, `time_alternatives` (aynı rota / aktarma / ertesi gün / akşam teslim noktası + SMS)
  - `config`: `routing.repair_limits`, `repair_max_extra_min: 0`, `repair_max_extra_km: 0.5`, `time_blocked_diff`, `time_alternatives`; `delivery_time.py`: `alternative_text`, `REASON_TEXT`, `OPTION_NAME` Bekleme tahmini ±`repair_wait_margin_min` (30 dk) paylı pencereyle yapılır; zaman onarımı ve aktarmada öğle penceresi ihlali de bu geniş payla sayılır; km sınırı pencere + zaman birlikte onarım öncesine göre.
  - `engine.py` kol D: kısıt + alternatifler (uygulanmaz, yalnız raporlanır); `export.py`: `summary.time_analysis.{constraint, overtime_route, alternatives}`, `time.json → alternatifler`, `plan.limits` / `plan.time_blocked`, `meta.time_example` kısıt şartı + `meta.time_example_constraint`, `route_minutes_per_day`
  - `ablation.py`: `full_tol5`, `no_time_tol5`, `unconstrained`, `no_time_unconstrained`; `time_contribution` yeni sütunlar
  - Test: `sim/tests/test_repair_limits.py` (7 hızlı); `test_anchored.py` güncellendi; sim toplamı 31 hızlı + 4 yavaş
  - _Gereksinimler: 21.1–21.9_
