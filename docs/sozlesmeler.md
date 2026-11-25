# Parçalar arası sözleşmeler

Proje üç parçadan oluşur. Her parça yalnızca bu belgedeki sözleşmeye dayanır; böylece üç kişi birbirini beklemeden çalışabilir.

| Parça | Klasör | Üretir | Tüketir |
|---|---|---|---|
| 1. Simülatör | `sim/` (`cm_sim`) | Çalıştırma klasörü (§1) | — |
| 2. Ajanlar | `agents/` | Ajan sonuçları (§3) | Çalıştırma klasörü (§1) |
| 3. API + arayüz | `api/`, `ui/` | REST API (§4), demo sayfası | Ajanlar (§3), çalıştırma klasörü (§1) |

**Hazır uygulama verisi (1 aylık geçmiş):** `data/demo_run/` her zaman geçerli bir çalıştırma klasörüdür. 2. ve 3. parça simülatörü beklemeden bununla çalışır. Yeniden üretmek için:

```
python -m cm_sim.run --demo --out runs
```

Ardından çıkan klasör `data/demo_run/` olarak kopyalanır (`python -m cm_sim.publish`).

---

## 1. Çalıştırma klasörü

Her JSON dosyasının kökünde `"app_data": true` alanı vardır. Gün numaraları global iş günüdür:
- 0'dan başlar; Pzt–Cmt arası, haftanın günü = `gün % 6`.
- İlk `warmup_days` gün ısınmadır, değerlendirme günleri `meta.eval_days` listesindedir.

| Dosya | İçerik |
|---|---|
| `meta.json` | `run_id`, `seed`, `scenarios`, `warmup_days`, `eval_days[]`, `weekday_names[]`, `arms{A,B,C,D: label}`, `band[2]`, `critical{day, eval_index, courier, courier_name, memory_gain?}`, `depot[lat,lng]`, `center`, `label`, `stop_fields[]`. `critical`: komşu şubeden "kim gitsin" seçiminin yapıldığı gün (gelebilecek ödünç > kullanılan) önceliklidir; `memory_gain` = o kuryenin aynı rota karşı-olgusu `{memoryless_min, hint_only_min, memory_min, mins, fails_memoryless, fails_memory}` (§6). `time_example` (Faz 2b, §7): seçilmiş teslim zamanı örneği ya da `null`. |
| `summary.json` | `arms.{A..D}`: `first_attempt_rate`, `preventable_fail`, `fail_by_reason{}`, `couriers_per_day`, `vehicle_days`, `km_per_day`, `in_band_share`, `workload_cv`, `door_minutes_per_stop`, `unfamiliar_share`, `memory_coverage`, `hint_helped`, `wrong_hint`, `notes`, `deferred`, `overtime_minutes_per_day`, `window_hits_per_day`, `window_wait_minutes_per_day`, `wasted_trips_per_day`, `plan_deferred_stops`, `wrong_deferrals`, `eta_abs_error`. Ayrıca `deltas.{C_vs_B, D_vs_C, D_vs_B, D_vs_A, B_vs_A}`: `first_attempt_pp`, `preventable_fail_pct`, `vehicle_days_pct`, `km_pct`; `memory_routing` (§6) ve `harvest{question, handover, answer, record, no_info, falling, target_stop, day}`. Faz 2b: kol başına `recipient_absent_per_day`, `revisit_stops_per_day`; `time_analysis` (§7). |
| `daily.json` | `arms.{A..D}[]`: gün bazında metrikler (`day`, `first_attempt_rate`, `preventable_fail`, `fail_by_reason`, `couriers`, `km`, `in_band_share`, `workload_cv`, `unfamiliar_share`, `memory_coverage`, `hinted_stops`, `hint_helped`, `wrong_hint`, `notes`…) |
| `learning_curve.json` | `arms.{A..D}.{courier_id}`: `{kind, days:[{day, rate, unfamiliar_share, hinted, preventable_per100, door_min_per_stop, minutes}]}`; `same_route.{courier_id}`: `{kind, days:[{day, hafizasiz{preventable_per100, minutes, fail}, hafizali{…}}]}` (kol D, aynı rota karşı-olgusu). Yalnız yeni, ödünç ve yedek kuryeler. |
| `recovery.json` | Uyum tahmincisinin doğrulaması: `end_of_warmup` ve `end_of_eval_C` için `{n, spearman_estimate, spearman_naive, eta_hat, nav_min_hat}` |
| `blocks.json` | `rows`, `cols`, `dlat`, `dlng`, `fields=[id,row,col,kind,lat,lng]`, `blocks[][]`. lat/lng blok merkezidir. |
| `addresses.json` | `fields=[id,lat,lng,kind,block,label]`, `addresses[][]` |
| `couriers.json` | `couriers[]`: `{id, name, kind, start_day, end_day, leave_days[]}`. Gizli özellik içermez. |
| `snapshots/{A,B,C,D}/{gün}.json` | Günün rotaları (aşağıda) |
| `assign/{C,D}/{gün}.json` | Atama girdisi: kurye × küme matrisleri (aşağıda) |
| `memory/{gün}.json` | D kolunda günün başındaki hafıza: `entries[]` (`id, address, kind, text, sources, first_day, last_day, temporary, ttl_until`) |
| `notes.json` | Gözlemlenebilir kurye notları: `{id, day, minute, courier, lat, lng, barcode, text}` |
| `notes_truth.json` | **Gizli karşılık** (yalnız değerlendirme): `{id, address, quirk_id, kind, stated_kind, version, pii, difficulty}` |
| `truth.json` | **Gizli gerçek** (yalnız değerlendirme): kurye becerileri, püf noktaları, `presence{profiles[], profile[adres → indeks], m[adres]}` (Faz 2b bulunabilirlik profili; demo `SeniorSimulator` saat teyidi cevabı buradan) |
| `parse_stats.json`, `report.md`, `config.yaml` | Hafıza ayrıştırma istatistikleri, okunabilir rapor, kullanılan yapılandırma |
| `sweep.json` | Sağlamlık taraması: `keys`, `values`, `rows[{params, arms, order_D_ge_C_ge_B, pp{C_vs_B, D_vs_C, D_vs_A}, D_vs_A_seed_min, D_vs_A_seed_max, courier_pct_D_vs_A, overtime_D_vs_A}]`, `order_share` (önemsiz sıralama; manşet değil), `headline{D_vs_A_pp{min, max, median, share_ge_0, share_abs_le_0_15, seed_spread_mean}, D_vs_C_pp{min, max, median, share_gt_0}, courier_day_D_vs_A_pct{min, max, median}}` |
| `learning.json` | Hedef 1 işe alım deneyi (`cm_sim.learning`, §6): `series.{C, D, D_memoryless}[{day, preventable_100, alt, top, n, route_min, door_min_per_stop}]`, `senior_mean{C, D}`, `mastery_day{C, D, threshold}`, `first_week.{C, D, D_memoryless}{preventable_fails[ort, alt, ust], route_min[…], n_courier}`, `first_week_paired_diff_C_minus_D{preventable_fails, route_min, n}` |
| `ablation.json` | Hafızanın parçaları (`cm_sim.ablation`): `variants.{hint_only, hint_harvest, hint_route, full, no_time, full_g60, no_time_g60}.{D_vs_C_pp, D_vs_A_pp, D_vs_C_preventable_pct, overtime_D_minus_C, km_D_minus_C, couriers_D_minus_C, window_hits_D, wasted_D, memory_coverage_D, D_far_pct, recipient_absent_D, revisit_D, fail_D, km_D, overtime_D, recipient_absent_D_minus_C, revisit_D_minus_C}{mean, min, max}` + `setting[]`; `time_contribution.{g20, g60}.{D_far_pct, recipient_absent_D, revisit_D, fail_D, km_D, overtime_D}{mean, min, max}` (aynı seed'de tam − zamansız; g60 = 60 günlük ısınma, geçmiş derinliği duyarlılığı) |
| `harvest.json` | Kol D'nin günlük hasat istatistiği: `days[{day, question, handover, answer, record, no_info, falling, target_stop}]` |
| `long_term/` | 60 iş günlük ikinci çalıştırma (snapshot'sız): `meta.json`, `summary.json`, `daily.json`, `learning_curve.json`, `recovery.json`, `parse_stats.json`, `harvest.json`, `report.md` |
| `calibration.json` | Uygulama verisinin saha verisinden türetilmiş toplu hedeflere uyumu: `rows[{measure, explanation, target, value, compatible}]` |
| `token_usage.json` | Ajan çağrısı başına token: `agents.{propose_assignment, ask_assignment, memory, briefing, orchestrator, ask_orchestrator, harvest}.{request, input, output, cached_read, cached_write, source}` (`source`: `estimate` ya da `measurement`). Orkestratör ve hasat tahmini, kurallı yedeğin izinden kurulan çağrı dizisiyle ölçülür. |
| `economics.json` | Varsayılan varsayımlarla ekonomi sonucu (`GET /api/economics` ile aynı biçim) |
| `delivery_log.json` | **Faz 2b.** Gözlemlenebilir teslim kaydı (kol D: ısınma + değerlendirme), bulunabilirliği sınayan denemeler: `fields=[day,address,minute,absent]`, sütun dizileri `day[]`, `address[]`, `minute[]` (varış, 00:00'dan dk, tamsayı), `absent[]` (1 = alıcı yok, 0 = teslim). Teslim zamanı analizi yalnız `day < hedef gün` satırlarını kullanır (§7). |
| `time.json` | **Faz 2b.** `days[{day, finding, confirmation, eligible, route, carried, correct, expected_before, expected_after}]` + `summary` (= `summary.time_analysis`) |

**Anlık görüntü (`snapshots/{arm}/{gün}.json`):**
```json
{"app_data": true, "run_id": "...", "arm": "D", "day": 34, "eval_index": 14, "weekday": 4, "weekday_name": "Cum",
 "depot": [lat, lng],
 "stop_fields": ["address","lat","lng","n","eta","ok","fail","deferred","reason","hint","unfamiliar"],
 "routes": [{"route": 3, "zone": null, "courier": "O03", "courier_name": "Onur", "courier_kind": "borrowed",
             "covered_by": null, "km": 41.2, "minutes": 472.0, "planned_minutes": 455.0,
             "stops": [[1234, 39.01, 35.02, 2, 642, 2, 0, 0, null, 1, 1], ...],
             "hints": {"1234": ["Zil çalışmıyor; alıcıyı telefonla arayın."]},
             "plan": {"plain_order": [1234, ...], "plain_km": 40.9, "plain_planned_minutes": 440.0,
                      "deferred": [{"address": 2211, "n": 1, "kind": "saturday_closed", "entry": "M00412", "outcome": "dogru|yanlis"}],
                      "changes": [{"type": "window", "address": 3456, "old_order": 36, "new_order": 34, "old_arrival": 722,
                                   "new_arrival": 710, "extra_km": 0.18, "window": [720, 810], "record": "M01776"}],
                      "extra_service": {"1234": 2.0}},
             "counterfactual": {"memoryless": {"minutes", "km", "ok", "fail", "preventable_fail", "deferred", "window_hits",
                                              "window_wait", "wasted", "stops"}, "hint_only": {…}, "memory": {…}}}]}
```
- `plan` ve `counterfactual` yalnız kol D'de (§6). Faz 2b: `plan.time_fail{before, after, finding}`, `plan.changes[]` içinde `type: "time"` (§7); `counterfactual.no_time` (zaman onarımı yokken aynı rota) ve zaman onarımı rotayı değiştirdiyse `counterfactual.time_stops{"address": {zamansiz: {varis, ok, fail, neden}, hafizali: {…}}}`; route özetlerinde ayrıca `recipient_absent`, `revisit`. `stops` yürütülen (hafızalı) sıradadır; plandan çıkan duraklar `plan.deferred`'dadır, `stops`'ta yoktur.
- `eta`: 00:00'dan itibaren dakika.
- `reason`: `recipient_absent` (Faz 2b: durak düzeyinde, varış saatine bağlı) `| address_not_found | closed | entry_failed | recipient_unreachable | wrong_deferral | other | null`. `wrong_deferral`: hafıza "bugün kapalı" dedi, durak plandan çıktı ama aslında açıktı (bilgiyle önlenebilir; başarısız sayılır).
- `hint` ve `unfamiliar`: 0/1.
- `deferred > 0`: kapalı olduğu bilindiği için planlı erteleme.

**Atama girdisi (`assign/{arm}/{gün}.json`):**
```json
{"app_data": true, "arm": "D", "day": 34, "weekday_name": "Cum",
 "couriers": [{"id": "K01", "name": "Mehmet", "kind": "senior"}, ...],
 "clusters": [{"id": 0, "stops": 80, "shipments": 120, "planned_minutes": 455.0, "km": 38.1, "center": [lat, lng], "blocks": [..]}],
 "matrix_fields": ["exp_fail","exp_min","unfamiliar","covered_unfamiliar","cost"],
 "exp_fail": [[...]], "exp_min": [[...]], "unfamiliar": [[...]], "covered_unfamiliar": [[...]], "cost": [[...]],
 "chosen": {"0": "K07", ...}, "totals": {...}, "unavailable": [{"id","name","kind"}]}
```
Matris satırları `couriers` sırasında (yalnız müsait kuryeler), sütunlar `clusters` sırasındadır.
- `cost = 1,0 × exp_fail + 0,05 × exp_min`
- `unfamiliar`: kuryenin yabancı olduğu durak sayısı.
- `covered_unfamiliar`: bunların hafızada notu olanları.

**Barkod biçimi:** `SN` + gün (2 hane) + adres (5 hane) + sıra (2 hane), ör. `SN340123401`.

## 2. Simülatörün Python arayüzü (`cm_sim`)

- `cm_sim.config.load_config(path=None, scenarios=[], overrides=["a.b=c"]) -> Config`
- `cm_sim.engine.Simulation(cfg).run() -> SimResult`
- `cm_sim.export.export_run(res, out_root) -> Path`
- `cm_sim.policies.base`: `AssignmentPolicy`, `MemoryPolicy`, `StopView`, `ClusterView`, `CourierView`, `HintView`, `DayContext`, `AssignmentDecision`
- `cm_sim.estimation`: `estimate(...)`, `expected_cost(...)`, `solve_assignment(cost, courier_ids, cluster_ids, exclude=set(), fixed={}) -> {küme: kurye}`
- `cm_sim.demand.parse_waybill(barkod) -> (gün, adres, sıra) | None`

### Kabul testlerinin kullandığı arayüz (isimler birebir)

Yeniden kurulumda bu isimler ve imzalar korunmalıdır. Testler: `sim/tests`, `agents/tests`, `api/tests`.

| Modül | İsimler |
|---|---|
| `cm_sim.config` | `load_config(path=None, scenarios=[], overrides=[]) -> Config`, `ConfigError` (geçersiz alanda alan yolunu içeren mesaj), `Config` alanları `default.yaml` ile birebir (ekstra alan yasak) |
| `cm_sim.world` | `build_world(cfg) -> World`; `World` (alanlar: `addr_xy, addr_latlng, addr_block, addr_kind, addr_label, addr_recurring, addr_demand_w, block_xy, block_kind, block_difficulty, quirks_by_addr, depot_xy`…); `Quirk(id, address, kind, temporary, active_from, active_to, change_day)` |
| `cm_sim.couriers` | `Courier(id, name, kind, skill, speed, note_propensity, home_zone, start_day, end_day, leave_days)` |
| `cm_sim.demand` | `demand_for_day(cfg, world, day, rates=None) -> np.ndarray`, `base_rates`, `weekday`, `waybill`, `parse_waybill` |
| `cm_sim.planning` | `plan_dynamic(cfg, world, stops, counts, n_available, rng) -> list[Route]`, `n_clusters`, `make_route`, `plan_fixed`, `fixed_zones` |
| `cm_sim.rng` | `day_streams(seed, day, counts) -> DayStreams` (`u_stop, u_ship, ...`) |
| `cm_sim.engine` | `Simulation(cfg)`; `.policies` sözlüğü (`"B"`: `assign`, `"C"`/`"D"`: `plan(ctx, stops, couriers, k, seed, extra_w=None)`); `.run() -> SimResult` (`arms[A..D].daily`, `.history`, `.fam`, `.routes`, `.counterfactuals`, `.harvest_stats`, `eval_days`, `world`, `couriers`, `elapsed`) |
| `cm_sim.routing_memory` | `StopRule`, `rule_from_entries(entries, weekday, lunch, extra_map, min_sources_closed)`, `plan_route(xy, depot_xy, plain_addrs, base_svc, rules, *, road_factor, mpk, start, scale, margin, defer_closed, window_repair, service_correction, time_repair=False, revisit_min=10, km_cost_min=0.8, min_gain_min=0.5) -> {order, deferred, km, planned, plain_km, plain_planned, changes, extra, time_fail}`, `repair_windows`, `repair_times`, `expected_time_fails`, `arrivals`. `StopRule.presence`: dilim başına tahmini bulunamama (Faz 2b). Saf fonksiyonlar; kol D ve `agents.route` aynısını çağırır. |
| `cm_sim.delivery_time` | **Faz 2b.** `SLOT_NAMES` (5 dilim: 09–12, 12–14, 14–16, 16–18, 18 sonrası), `BORDERS=(720, 840, 960, 1080)`, `slot(mins)`, `day_type(haftagünü)`, `TimeRecord(n_adres).add(gün, adres, haftagünü, dk, bulunamadı)` (`att`, `abs`: (n_adres, 2, 5)), `counts_from_log(n_adres, gün[], adres[], dk[], bulunamadı[], before_day)`, `Params.from_dict(cfg.time_analysis)`, `time_findings(att, abs, tür_indeksi, n_tür, adresler, haftagünü, P) -> {adres: bulgu}`, `address_finding`, `fits_route(finding, min_level)`, `proposal_text(finding)`. Saf; kol D ve `agents.delivery_time` aynısını çağırır. |
| `cm_sim.learning`, `cm_sim.ablation` | `python -m cm_sim.learning [--seeds 12]` → `runs/learning/learning.json`; `python -m cm_sim.ablation [--seeds 3]` → `runs/ablation/ablation.json`; `publish` ikisini kopyalar |
| `cm_sim.history` | `HistoryReader(history, fam, unfamiliar_below, block_kind=None)`; iç öznitelikler `_h` (History) ve `_f` (Familiarity, `.state`) testte gezilir; `familiar_blocks(courier, day, min_f)` |
| `cm_sim.estimation` | `solve_assignment(cost, courier_ids, cluster_ids, exclude=set(), fixed={})`, `report_recovery(history_reader, true_skill, assignment_cfg) -> {spearman_estimate, spearman_naive, ...}` |
| `cm_sim.export` | `export_run(res, out_root, snapshots=None) -> Path`, `STOP_FIELDS` |
| `cm_sim.run` | `DEMO_SCENARIOS = ["leave_wave", "turnover", "borrowed_courier", "volume_shock"]`, `main(argv)` |
| `cm_sim.calibration` | `measure(cfg) -> dict` (anahtarlar `calibration.yaml → hedefler` ile aynı) |
| `agents` | `Services.create(run_dir=None, mode=None, memory_file=None)` → `.run, .llm, .book, .assignment, .memory, .briefing, .orchestrator, .sessions, .harvest` (her ajanın kendi `.llm`'i; `.harvest` = `HarvestStore`, ajanı `.harvest.agent`) |
| `agents.llm` | `LLM(mode, model, region, cassette_dir)`, `LLM._call(agent, req) -> dict` (testlerde ezilir), `run_agent(...)`, `Tool(name, description, input_schema, fn=None, summarize=None)`, `obj(properties)`, `nullable(schema)`, `AgentError`, `CassetteMiss` |
| `agents.guardrails` | `find_pii(text) -> list[str]`, `redact(text) -> str` |
| `agents.memorybook` | `MemoryBook(run, path)`, `MemoryWriteError`, `upsert(address, kind, text, day, note_id, source="agent", window=None)`, `for_address`, `feedback`, `reset`, `ensure`. Kayıtta isteğe bağlı `pencere: [başlangıç, bitiş]` (dk; yalnız `lunch_break`) ve `source_list[]` |
| `agents.memory` | `classify(text) -> tür \| None`, `parse_window(text) -> [head, bit] \| None` |
| `agents.tr` | `dative(n)`, `name_dative(name)`, `num(x, nd=1, sign=False)`, `hhmm(minute)` |
| `agents.economics` | `compute(run, tokens, assumptions)`, `load_assumptions(overrides=None)`, `load_tokens(run)` |
| `agents.rundata` | `RunData(run_dir=None)`, `parse_waybill` |
| `api.main` | `app` (FastAPI), `sv()` + `sv.cache_clear()` |

Ajanlar yalnızca `solve_assignment` ve `parse_waybill` saf fonksiyonlarını içe aktarır. Bunlar da kopyalanabilecek kadar küçüktür. Ajanların geri kalanı çalıştırma klasörünü okur.

## 3. Ajan katmanı (`agents`)

| Modül | Sorumluluk |
|---|---|
| `agents.llm` | `LLM` sınıfı. Modlar: `mock` (LLM yok, deterministik yedek), `live`, `record`, `replay`. `CM_LLM_MODE` ortam değişkeni seçer. Canlı çağrı hata verirse ajan `mock` yedeğine düşer ve sonuçta `degraded: true` döner. |
| `agents.rundata` | `RunData(run_dir)`: meta, kuryeler, adresler, anlık görüntüler, atama girdileri, hafıza anlık görüntüleri, notlar |
| `agents.memorybook` | `MemoryBook`: canlı adres hafızası (JSON dosyası), bir günün D hafızasından tohumlanır |
| `agents.guardrails` | Kişisel veri tespiti/ayıklama (telefon, "hanım/bey" ile ad, yaş/sağlık/yargı sözcükleri) |
| `agents.assignment` | `AssignmentAgent.propose(day)`, `.ask(day, question, history)` |
| `agents.memory` | `MemoryAgent.process(day, courier, text, lat, lng, barcode, minute, note_id=None, address_id=None, source="agent")`. `address_id` verilirse (hasat cevabı) adres aranmaz. Öğle arası notunda pencere metinden çıkarılır (`parse_window`). |
| `agents.briefing` | `BriefingAgent(run, book, llm, plans=None).prepare(day, courier)`: rota onaylı plandan (`SessionStore.plans`, yoksa simülasyon planı), dönüş saati `EtaModel`'den, hafızanın rota değişiklikleri brifingde; ipuçları güne/saate göre süzülür (`hint_today_valid`) |
| `agents.harvest` | `HarvestTools` (`memory_gaps`, `recurring_failure`, `save_questions`), `HarvestAgent.plan(gün, iz)`, `HarvestStore` (`plan`, `items`, `reply(question_id, text)`, `simulate_answer(question_id)`), `SeniorSimulator` (demo: cevap gizli gerçekten, `simulate: true`) |
| `agents.evaluate` | Hafıza Ajanı'nı `notes_truth.json` ile ölçer, `parse_accuracy` önerir |
| `agents.cost` | Ajan çağrısı başına token: canlı ölçüm (`data/usage.jsonl`) varsa o, yoksa temsili çağrı dizilerinden tahmin → `token_usage.json` |
| `agents.economics` | Token maliyeti ↔ kazanç (`agents/economics.yaml` varsayımları) → `economics.json`; `compute(run, tokens, assumptions)` |
| `agents.check`, `agents.record` | Bedrock bağlantı + mini ajan döngüsü kontrolü; demo akışını kayıt-oynat için kaydetme |
| `agents.trace` | `Trace`: ajan izi (olay sırası, dinleyici). Biçim §5 |
| `agents.route` | `RouteConstraint`, `ConstraintSource`, `NoConstraints`, `MemoryConstraints(book, run)`, `EtaModel`, `RoutePlanner(run, source).plan(gün, küme, kurye, expected_min, hafıza_sayacı)`: düz sıradan `cm_sim.routing_memory.plan_route` ile hafızalı rota; çıktı §6 |
| `agents.delivery_time` | **Faz 2b.** `TimeData(run)` (`counts(gün)`, `findings(gün, adresler)`, `address_table(adres, gün)`, `history(adres, gün)`), `TimeSource` (`route(gün, adresler)`, `make_selection(gün, min_confidence, haric)`, `write_confirmation(adres, gün, teyit, saat, metin)`, `row`, `reset`), `time_source(run)` (çalıştırma başına tek), `delivery_time_analysis(...)`, `parse_confirmation(metin) -> (evet/hayır/None, dk/None)` |
| `agents.orchestrator` | `DayTools` (araçlar), `Orkestrator.plan(gün, iz)`, `.ask(gün, soru, oneri, iz, gecmis)`, `.apply_decision(gün, oneri, karar, atama, not)`, `SessionStore` (`start`, `get`, `decision`, `ask`, `plans`) |

Ajan istemleri `agents/prompts/*.md` dosyalarındadır (Türkçe). Ajan sonuçlarının JSON biçimi §4'teki yanıt gövdeleriyle aynıdır.

## 4. REST API (`api.main:app`)

Tüm yanıtlar JSON'dur. Ajan yanıtlarında şu alanlar ortaktır:
- `mode`: `mock|live|record|replay`
- `degraded`: bool
- `steps[]`: ajanın çağırdığı araçlar, `{tool, input, summary}`

| Yöntem ve yol | Gövde / parametre | Yanıt |
|---|---|---|
| `GET /api/status` | — | `{mode, model, region, run_id, app_data, cassettes, memory_seed_day, models{assignment, memory, briefing, orchestrator, harvest}}` |
| `GET /api/meta` | — | `meta.json` |
| `GET /api/summary` | — | `{summary, daily, learning_curve, learning_same_route, recovery, sweep\|null, long_term\|null, calibration\|null, learning\|null, ablation\|null, time\|null}`. `daily` ve `learning_curve` doğrudan kol sözlüğüdür; `learning` Hedef 1 deneyidir; `long_term` = `{summary, daily, learning_curve, meta}`. |
| `GET /api/learning` | — | `learning.json` (Hedef 1) ya da 404 |
| `GET /api/economics` | `?scenario=cautious\|optimize&usd_try=&courier_daily_cost_tl=&km_cost_tl=&fails_other_tl=&second_attempt_min=&daily_assignment_question=&model_assignment=&model_memory=&model_briefing=&cache=` | Ekonomi sonucu (aşağıda). Önce senaryo uygulanır, sonra model ve önbellek parametreleri tek tek ezer. |
| `GET /api/blocks` | — | `blocks.json` |
| `GET /api/couriers` | — | `couriers.json` |
| `GET /api/day/{arm}/{day}` | — | anlık görüntü (§1) |
| `POST /api/assignment/propose` | `{day}` | Atama sonucu (aşağıda) |
| `POST /api/assignment/ask` | `{day, question, history:[{role: "manager"\|"agent", text}], current?:[{cluster, courier}]}` | `{response, assignment\|null, total\|null, diff\|null, mode, degraded, steps}`. `diff` = `{expected_fails, unfamiliar_stop, memory_unfamiliar, changed_clusters[]}`; `current` verilmezse onaylanmış atama, o da yoksa öneri temel alınır. |
| `POST /api/assignment/approve` | `{day, assignment:[{cluster, courier}]}` | `{ok}` |
| `GET /api/briefing/{day}/{courier}` | — | Brifing sonucu (aşağıda) |
| `POST /api/note` | `{day, courier, text, lat?, lng?, barcode?, minute?}` | Not sonucu (aşağıda) |
| `GET /api/memory` | `?day=&address=` | `{entries[]}` |
| `GET /api/memory/summary` | `?day=` | `{total, type_distribution{}, last[]}` |
| `POST /api/memory/feedback` | `{day, record, valid}` | `{ok, record\|null}` |
| `GET /api/cards/{day}/{courier}` | `?all=true` | **Faz 2d** durak bilgi kartları (§11); 404: kurye/gün yok ya da kurye planda yok |
| `POST /api/approach` | `{day, courier, lat, lng, next_order?, shown?[]}` | **Faz 2d** şimdi söylenecek kartlar (§11); geçersiz `next_order` ya da koordinat 422 |
| `POST /api/review/run` | `{day}` | Değerlendirme Ajanı sabah raporu (§12) |
| `GET /api/review` | — | `{last_report, params, question_queue[]}` |
| `POST /api/review/decision` | `{day, n, decision: approve\|reject\|undo}` | Güncellenen akış olayı; olay yok 404, geçersiz karar 409 |
| `GET /api/feed` | `?after=&agent=&status=` | `{events[]}` ajan akışı (§12) |
| `POST /api/feed/reset` | — | `{ok}` |
| `GET /api/region/branch` | `?day=` | Şube katmanı + Bölge Ajanı'nın son raporu (`agent_report`, §12) |
| `POST /api/region/run` | `{day}` | Bölge Ajanı şube raporu (§12) |
| `GET /api/real-day/{day}` | — | Gerçek gün dosyası (§13); 404 yok, 422 biçim |
| `GET /api/real-day/{day}/memory` | — | Hafıza kapsamı ve beklenen başarısız teslim (§13) |
| `GET /api/real-day/{day}/cluster/{cid}` | — | Küme rotası, kartlar, yol, `cluster_card` (Bölge Ajanı) (§13) |
| `GET /api/real-day/{day}/transfer` | — | Kurye aktarımı senaryosu (§13; yeniden dengeleme YAKLAŞIK) |
| `POST /api/demo/reset` | `{day}` | Hafıza, ajan akışı, Değerlendirme parametreleri ve önbellekler baştan |
| `POST /api/memory/reset` | `{day}` | `{ok, total}` (Faz 2b: teslim zamanı seçimi ve saat teyitleri de sıfırlanır) |
| `GET /api/speech` | `?text=` | `audio/mpeg` (Polly yapılandırılmışsa) ya da 501. 501 gelirse arayüz tarayıcı sesine düşer. |
| `POST /api/orchestrator/start` | `{day}` | Koşu özeti (aşağıda); koşu arka planda sürer |
| `POST /api/orchestrator/plan` | `{day}` | Koşu özeti; koşu bitene kadar bekler |
| `GET /api/orchestrator/session/{id}` | `?after=n` | Koşu özeti; `events` n. olaydan itibaren (poll) |
| `GET /api/orchestrator/session/{id}/stream` | `?after=n&tempo_ms=0` | `text/event-stream`: her olay `id: i`, `event: <type>`, `data: <event JSON>`; planlama evresi bitince `event: last` `{status, total_event}` |
| `POST /api/orchestrator/session/{id}/decision` | `{decision: approval\|ret\|edit, assignment?: [{cluster, courier}], note?}` | `{status: finalized\|rejected, plan\|null, changed_clusters[], note, diff?}`. Onay beklemiyorsa ya da düzenleme geçersizse 400 |
| `POST /api/orchestrator/session/{id}/ask` | `{question, history?}` | Senaryo sonucu (aşağıda). Onay beklemiyorsa 409 |
| `GET /api/plan/{day}` | — | Kesinleşmiş plan (öneri biçimi) ya da 404 |
| `GET /api/orchestrator/candidates/{day}` | — | `{kapasite: capacity_gap çıktısı, adaylar: neighbor_candidates çıktısı}` ("kim gitsin" gerekçesi; LLM yok) |
| `GET /api/route/{day}/{courier}` | — | `compute_route` çıktısı (§6, §7) + `plan_source: approved_plan\|simulation_plan`. Canlı hafızayla; 404: kurye planda yok |
| `GET /api/time/example` | — | **Faz 2b** demo örneği (§7); 404: örnek yok |
| `GET /api/time/{day}` | `?min_confidence=low\|mid\|high` | `delivery_time_analysis` çıktısı + `selection` (§7); geçersiz güven 422 |
| `GET /api/time/{day}/address/{address}` | — | `{address, day, history[], table, finding\|null, confirmation\|null}` (§7); 404: gün/adres yok |
| `POST /api/harvest/plan` | `{day}` | Hasat sonucu (§6) |
| `GET /api/harvest/{day}` | — | `{day, mode, degraded, plan_source, summary, questions[]}` ya da 404 |
| `POST /api/harvest/answer` | `{question_id, text}` | `{question, memory: Not resultOf}`; `reason: "time"` sorusunda `{question, memory: null, time: {day, confirmation, hour, text, status: confirmation\|ret\|uncertain, hour_text, summary}}`. Bilinmeyen soru 404, cevaplanmış soru 409 |
| `POST /api/harvest/simulate-answer` | `{question_id}` | Aynı biçim; cevap gizli gerçekten üretilir (demo, `question.simulate = true`) |

**Koşu özeti (orkestratör):**
```json
{"session_id": "G32-001", "day": 32, "status": "calisiyor|awaiting_approval|kesinlesti|reddedildi|hata", "events": [/* §5 */],
 "total_event": 24, "proposal": {/* aşağıda */}, "mode": "mock", "degraded": false, "plan": null, "error": null}
```

**Öneri (`proposal`, ayrıca `plan`):**
```json
{"day": 32, "weekday": "Çar", "borrowed": [{"id": "O01", "name": "Onur", "source_branch": "Komşu şube"}], "exclude": [],
 "assignment": [{"cluster": 24, "courier": "O01", "courier_name": "Onur", "courier_type": "borrowed", "source": "komsu|yerel", "stop": 112,
            "shipment": 130, "expected_fails": 9.9, "unfamiliar_stop": 112, "memory_unfamiliar": 20, "expected_min": 581,
            "planned_min": 395.8, "cost": 39.0, "extra_clusters": [], "over_band": true, "center": [39.0, 35.0]}],
 "total": {"courier_count": 26, "expected_fails": 149.3, "unfamiliar_stop": 377, "memory_unfamiliar": 66, "over_band_courier": 8,
            "over_band_min": 473, "expected_min_total": 12637, "cost": 744.8},
 "own_zone_share": 0.875, "distributed_clusters": [], "eta_model": {"a": 0.861, "b": 1.014, "history_route": 234, "mean_absolute_error_min": 30.3},
 "dispatch_note": null, "idle_couriers": [], "comparison": {"history_blind_expected_fails": 212.2},
 "rationale": ["..."], "risks": ["..."], "questions": ["Onur gelmezse ne olur?"]}
```
- `expected_min`: `EtaModel` tahmini (kuryeye özgü); `planned_min`: planlama motorunun süresi. `over_band`: `expected_min > band[1]`.
- `distributed_clusters`: kurye küme sayısından azsa atanamayan küme(ler) ve onu alan kuryelerin ek süresi (yaklaşık): `[{cluster, stop, fields: [{cluster, courier, name, extra_min}]}]`.

**Senaryo sonucu (orkestratör `ask`):**
```json
{"response": "Onur gelmezse iki yol var. (1) ... (2) ...", "new_proposal": {/* öneri biçimi */}, "diff": {"expected_fails": 0.0,
 "over_band_min": 0, "over_band_courier": 0, "unfamiliar_stop": 0, "memory_unfamiliar": 0, "courier_count": 0, "changed_clusters": [24]},
 "alternatives": [{"name": "Komşu şubeden Melis", "plan_change": {"borrowed": [], "exclude": [], "pin": []}, "total": {}, "diff": {}, "score": 172.9},
                   {"name": "Kimse gelmezse", "...": "..."}],
 "day": 32, "mode": "mock", "degraded": false, "trace": [/* bu sorunun olayları */]}
```

**Atama sonucu:**
```json
{"day": 34, "mode": "mock", "degraded": false,
 "assignment": [{"cluster": 0, "courier": "K07", "courier_name": "Murat", "courier_type": "senior", "stop": 80, "shipment": 120,
            "expected_fails": 4.1, "unfamiliar_stop": 3, "memory_unfamiliar": 1, "planned_min": 455.0, "center": [lat, lng]}],
 "total": {"expected_fails": 127.1, "unfamiliar_stop": 178, "memory_unfamiliar": 37, "cost": 566.6},
 "comparison": {"history_blind_expected_fails": 171.3},
 "on_leave": [{"id": "K03", "name": "Mustafa", "type": "senior"}], "idle_available": [{"id": "Y02", "name": "...", "type": "reserve"}],
 "rationale": ["..."], "highlights": ["..."], "steps": [{"tool": "solve_assignment", "input": {}, "summary": "..."}]}
```

**Brifing sonucu:**
```json
{"day": 34, "courier": "O03", "courier_name": "Onur", "courier_type": "borrowed", "mode": "mock", "degraded": false,
 "morning_briefing": "Günaydın Onur. Bugün 83 durak...",
 "door_sentences": [{"address": 1234, "sentence": "Zil çalışmıyor, alıcıyı arayın.", "order": 12,
                     "records": [{"id": "M00412", "type": "bell", "text": "Zil çalışmıyor; alıcıyı telefonla arayın."}]}],
 "warnings": ["14 numaralı durağa varış öğle arasına denk geliyor."],
 "route": {"route": 3, "courier": "O03", "stops": [[...]], "hints": {...}, "minutes": 472.0, "km": 41.2},
 "steps": []}
```
- `route`: anlık görüntüdeki rota nesnesidir (D kolu).
- `stop_fields`: brifing yanıtında da üst düzeyde döner, ayrıca `meta.json`'da bulunur.
- `order`: 1 tabanlı durak sırası.
- `records`: "hâlâ geçerli mi?" geri bildirimi için hafıza kayıtlarıdır.
- D kolunda atama tablosundaki `cluster`, anlık görüntüdeki `route` ile aynıdır.

**Not sonucu:**
```json
{"status": "saved", "address": {"id": 1234, "label": "Blok 12-07 No 3", "type": "apartment", "lat": 39.01, "lng": 35.02},
 "type": "bell", "hint": "Zil çalışmıyor; alıcıyı telefonla arayın.", "record": {"id": "M00412", "sources": 2},
 "personal_data_redacted": true, "summary": "Not adrese bağlandı; kişisel bilgi kaydedilmedi.", "question": null,
 "mode": "mock", "degraded": false, "steps": [...]}
```
`status` değerleri:
- `saved`: yeni kayıt.
- `updated`: var olan kayıt güçlendi.
- `noise`: adresle ilgisiz not.
- `uncertain`: adres çözülemedi; `question` alanı kuryeye sorulacak soruyu taşır.
- `rejected`: içerik kaydedilemez.

**Püf noktası türleri:** `back_entry, saturday_closed, lunch_break, safety, bell, position_wrong, reception, temporary_closed, roadwork`

**Ekonomi sonucu (`GET /api/economics`, `economics.json`):**
```json
{"app_data": true, "source_running": "long_term", "day_count": 60,
 "assumptions": {"usd_try": 45, "courier_daily_cost_tl": 3500, "courier_min_tl": 7.29, "km_cost_tl": 6, "failed_attempt_tl": 71.0, "...": "..."},
 "volume_day": {"shipment": 2812, "stop": 2375, "courier": 20.1, "note": 45.9, "llm_call": 70, "token": {"input": 452128, "output": 79253}},
 "llm": {"daily_tl": 152.7, "daily_usd": 3.39, "per_shipment_kurus": 5.43, "per_note_tl": 2.47, "per_briefing_tl": 0.5,
         "agents": {"memory": {"call_day": 45.9, "model": "anthropic.claude-opus-5-5", "token_call": {"input": 7479, "output": 1250},
                                "per_call_tl": 2.47, "daily_tl": 113.4, "source": "estimate"}, "...": "..."}},
 "gain": {"vs_C": {"comparison": "...", "prevented_fails_day": 7.7, "fails_tl_day": 547, "prevented_overtime_min_day": 113,
                     "overtime_tl_day": 1242, "gained_door_min_day": 200, "capacity_courier_hour_day": 3.3, "capacity_tl_day": 1458,
                     "direct_gain_tl_day": 1789, "net_tl_day": 1636, "return_multiple": 11.7, "total_gain_tl_day": 3247, "first_attempt_score": 0.27},
            "vs_B": {"...": "aynı alanlar (üst sınır)"}},
 "branch_annual": {"llm_tl": 46730, "net_tl_vs_C": 500616, "net_tl_vs_B": 11094336},
 "scale": [{"branch": 1, "llm_tl_year": 46730, "direct_gain_tl_year_vs_C": 547434, "net_tl_year_vs_C": 500616, "net_tl_year_vs_B": 11094336}],
 "model_comparison": [{"model": "anthropic.claude-opus-5-5", "name": "Claude Opus 5.5", "llm_tl_day": 152.7, "per_shipment_kurus": 5.43, "return_multiple_vs_C": 11.7}],
 "dynamic_planning": {"explanation": "...", "courier_day_diff": 2.5, "courier_cost_tl_day": 8750, "first_attempt_score_D_vs_A": 0.01, "first_attempt_score_B_vs_A": -2.05},
 "models": [{"id": "...", "name": "..."}], "warning": "Uygulama verisi · 1 aylık geçmiş. ..."}
```
- **Manşet karşılaştırma `vs_C`:** Hafıza ve Brifing'in uyumlu atamanın üstüne katkısıdır (temkinli).
- **`vs_B`:** Üç ajanın birlikte katkısıdır (üst sınır).
- **`dogrudan_kazanc`:** Önlenen başarısız denemeler ile önlenen fazla mesaiden oluşur.
- **`capacity`:** Vardiya içi kazanılan dakikadır; ayrı gösterilir, getiriye katılmaz.
- **`total_gain_tl_day`:** `direct_gain_tl_day + capacity_tl_day`.
- **`source` değerleri:** yalnızca `estimate` ya da `measurement` (ASCII).
- **`/api/summary` → `calibration.rows`:** `target` alanı API'de çıkarılır (şirket içi toplu özet); yalnız `measure, explanation, value, compatible` döner.
- **Parametre sınırları:** `/api/economics` parametreleri sınır dışındaysa 422 döner.

**Ekonomi: manşet, operasyon ve LLM senaryoları**
- **`headline`:** `{savings_tl_day, savings_tl_year, savings_rate, per_shipment_before_tl, per_shipment_after_tl, agentless_extra_cost_tl_day, agentless_extra_cost_tl_year, agents_saved_tl_day, quality{fails_per_day_current, fails_per_day_agentless, fails_per_day_memory}, llm_share, sentence}`. A (bugün) ile D (yeni yapı + Courier Memory) arasındaki operasyon maliyeti farkıdır.
- **`operation.arms.{A,B,C,D}`:** `{name, courier, fails_per_day, preventable_day, overtime_hour_day, km_day, first_attempt, components_tl_day{courier, overtime, fails, km, llm}, total_tl_day, per_shipment_tl, total_tl_year}`
- **`operation.waterfall[]`:** `{code: today|dynamic|agentless|assignment|memory|result, step, type: start|decrease|increase|result, tl_day}`. Ara adımların toplamı başlangıçtan sonuca götürür.
- **`operation.scale[]`:** `{branch, savings_tl_year, agentless_extra_cost_tl_year}`
- **`llm_scenarios[]`:** `{scenario, name, llm_tl_day, llm_tl_year, per_shipment_kurus, savings_rate, memory_return_multiple}`. Senaryolar `agents/economics.yaml → senaryolar` içindedir.
- **`scenario`:** Uygulanan senaryo adı ya da `null`.

**Simülasyon metrikleri (ek):**
- `daily.json` ve `summary.json` `in_band_planned_share` (planlanan süreyle vardiya bandı) ve `planned_cv` alanlarını taşır.
- "Kendi bölgesinde durak payı" = `1 − unfamiliar_share`.
- C ve D kolları çekirdek bölgeli dinamik plandır (`policies/simple.py → AnchoredPlanPolicy`); D, C'nin planını paylaşır ve ipucu alır.

## 5. Ajan izi (orkestratör)

Her olay: `{"i": sıra, "type": ..., "source": "llm|kural|insan", ...alanlar}`. Saat damgası yoktur; mock iz deterministiktir. Canlı yol ile kurallı yedek aynı tipleri aynı sırayla üretir; arayüz yalnız `source` ile ayırt eder.

| `type` | Alanlar | Ne zaman |
|---|---|---|
| `start` | `day, mod, task: plan\|ask, question?` | Koşu ya da soru başlarken |
| `decision` | `text` | Ajanın (canlıda modelin metin bloğu, mockta şablon) bir sonraki adım kararı/gözlemi |
| `tool` | `arac, girdi` | Araç çağrısı (bitiş araçları `present_proposal`, `respond` dahil) |
| `result` | `arac, ozet, veri` | Araç sonucu; `data` aracın tam JSON çıktısı |
| `error` | `arac, metin` | Araç hatası; ajana `is_error` ile geri verilir |
| `fallback` | `text` | Canlı/replay yolu tamamlanamadı, kurallı yedek devam ediyor |
| `proposal` | `proposal` | Müdüre sunulan öneri (§4) |
| `awaiting_approval` | — | İnsan onayı noktası; planlama evresi biter |
| `human_decision` | `decision, note, changed_clusters` | Müdürün kararı (`source: human`) |
| `response` | `yanit, fark` | Senaryo sorusunun cevabı |
| `done` | `durum, metin?` | Koşu kapandı (`finalized`, `rejected`, `error`) |

Araç adları ve girdileri (strict şema): `read_volume {}`, `capacity_gap {}`, `delivery_time_analysis {min_confidence}`, `apply_time_constraint {min_confidence, exclude[], rationale}` (Faz 2b, §7), `neighbor_candidates {need, exclude[], current_borrowed[]}`, `core_assignment {borrowed[], exclude[], pin[{cluster_id, courier_id}]}`, `compute_route {cluster_id, courier_id}`, `present_proposal {borrowed[], exclude[], pin[], rationale[], risks[], questions[]}`, `respond {response, plan_change: {borrowed[], exclude[], pin[]}|null}`.

**Rota aracı ve hafıza kısıtları (Faz 2 takılma noktası):** `compute_route` çıktısı her zaman `constraint_source`, `constraints[]` (`RouteConstraint`: `address, kind: closed_day|closed_window|extra_service|dogru_nokta|temporary_closed, weekday, window, extra_service_min, point, until_day, source`) ve `changes[]` taşır. Faz 1'de kaynak `offline`, listeler boştur.

---

## 6. Faz 2: hafıza rotayı değiştirir, hasat, öğrenme

**Hafıza → kısıt (simülatör ve ajan aynı kural, `cm_sim.routing_memory`):**

| Hafıza türü | Kısıt | Rotaya etkisi |
|---|---|---|
| `saturday_closed` | `closed_day` (haftagünü 5) | Cumartesi plandan çıkar (planda erteleme) — kayıt en az `routing.defer_min_sources` (2) kaynaklıysa; tek kaynaklıysa rotada kalır, kapıda ipucu |
| `temporary_closed` | `temporary_closed` (`until_day` = TTL) | Aynı kural (≥ 2 kaynak → plandan çıkar) |
| `lunch_break` | `closed_window` (`window` alanı ya da 12:00–13:30) | Beklenen varış (başlangıç + `time_scale` × geçen süre) pencereye ± `window_margin_min` düşüyorsa en az km artışıyla taşınır |
| `back_entry`, `safety`, `reception`, `roadwork` | `extra_service` (`routing.extra_service_min`) | Durak ağırlığına (kümeleme) ve planlanan süreye eklenir |

**`compute_route` çıktısı (Orkestratör aracı, `GET /api/route`):**
```json
{"cluster": 22, "courier": "O02", "name": "Gökhan", "stop": 82, "shipment": 99, "km": 29.5, "planned_min": 351, "expected_min": 436,
 "start": "09:00", "estimated_return": "16:16", "memory_stop": 19, "constraint_source": "memory",
 "constraints": [{"address": 38563, "kind": "closed_window", "window": [720, 810], "source": "M01776", "sources": 1, ...}],
 "changes": [{"type": "window", "address": 38563, "label": "Blok 28-21 No 57", "old_order": 36, "new_order": 34,
                    "old_arrival": 722, "new_arrival": 710, "extra_km": 0.178, "window": [720, 810], "record": "M01776", "text": "..."},
                   {"type": "deferred", "address": 2211, "reason": "saturday_closed", "record": "M00412", "shipment": 1, "text": "..."},
                   {"type": "extra_service", "stop": 19, "mins": 20.0, "text": "..."}],
 "same_as_sim": true,
 "comparison": {"memoryless": {"stop": 82, "km": 29.4, "planned_min": 331, "window_matching": 1, "closed_door_visit": 0, "order": [...]},
                   "memory": {"stop": 82, "km": 29.5, "planned_min": 351, "window_matching": 0, "closed_door_visit": 0, "order": [...]},
                   "diff": {"km": 0.06, "deferred": 0, "carried": 1, "window_matching": -1, "closed_door_visit": 0},
                   "simulation": {"memoryless": {...}, "hint_only": {...}, "memory": {...}}, "note": "..."}}
```
- `same_as_sim`: canlı hafıza = simülasyonun o günkü hafızası ise ajanın hafızalı sırası kol D'nin yürüttüğü sırayla birebir aynıdır (test: tüm günler, tüm rotalar). Not/hasat cevabı hafızayı değiştirince `false` olur ve rota değişir.
- `comparison.simulation`: anlık görüntüdeki `counterfactual` (aynı kurye, aynı duraklar, aynı rastgele sayılar).

**`summary.memory_routing`:** `{route_day, day, daily.{memoryless, hint_only, memory}.{minutes, km, fail, preventable_fail, window_hits, window_wait, wasted, deferred}, type.{senior, reserve, new, borrowed}.{route, min_gain_route_mean, min_gain_route_p10, _p50, _p90, route_share_min_route_mean, prevented_fails_route_mean}, note}`. Karşı-olgu kuryenin o günkü bilgisiyle yürütülür (hafıza olmasaydı kurye bazı püf noktalarını kendisi öğrenirdi; kol C bunu içerir).

**Hasat sonucu (`POST /api/harvest/plan`):**
```json
{"day": 32, "mode": "mock", "degraded": false, "plan_source": "approved_plan|simulation_plan", "summary": "25 boşluk sorusu, 4 teyit sorusu ...",
 "questions": [{"id": "H32-01", "day": 32, "courier": "K09", "courier_name": "İbrahim", "address": 1234, "label": "Blok 20-09 No 4",
              "question": "...", "reason": "bosluk|hipotez", "hypothesis_type": null, "status": "bekliyor|cevaplandi",
              "cevap?": "...", "simule?": true, "sonuc?": {"status", "type", "hint", "record", "summary"}}],
 "trace": [/* §5 biçimi: basla, karar, arac/sonuc (memory_gaps, save_questions, recurring_failure), arac:harvest_plan, bitti */]}
```
- Kurallar: kurye başına günde ≤ 3, şubede ≤ 30 soru; boşluk sorusu yalnız yerel (ödünç olmayan), bugün çalışan kuryeye; hipotez teyitsiz hafızaya yazılmaz.
- Cevap Hafıza Ajanı'ndan `address_id` ile geçer (`source="harvest"`); "bildiğim sorun yok" → `noise` (kayıt yok).

**Brifing sonucu (Faz 2 ek alanlar):** `plan_source`, `estimated_return` (EtaModel), `expected_min`, `route_changes[]` (`compute_route.changes`), `route_comparison`. `route_risks` aracı ayrıca `filtered_hint` (güne/saate uymadığı için söylenmeyen ipucu sayısı) ve `route_change_summary[]` döner.

**Simülatör tarafı:**
- Öğle arası: bilinse de pencere içinde gelinirse ek dakika `min(pencere sonu − varış, quirks.lunch_wait_max)`; bilinmiyorsa başarısızlık riski. (Faz 1'deki kestirme kaldırıldı.)
- `quirks.effects.*.known_minutes`: bilinen püf noktasının kalan süresi (kimlik işlemi, arkadan dolaşma).
- Kapı hızı tahmini (`estimation.speed`) yalnız tanıdık duraklardan (yabancı sokakta gözlenen kurye "yavaş" görünmez).
- `calendar.borrowed[]`: aynı kimlik birden çok dönem; `border_side/border_depth_km/border_familiarity`: komşu şubeyle ortak sınır sokaklarının tanıdıklığı.
- `memory.harvest_per_day`, `harvest_per_senior`, `p_answer`: kol D'de plan sonrası hasat (cevap kıdemlinin gizli bilgisinden; simüle insan).

---

## 7. Faz 2b: teslim zamanı analizi (kayıtlardan, notsuz) → rota

**Dünya (gizli gerçek):** her adresin bir bulunabilirlik profili vardır (`presence.profiles`: `home`, `worker`, `shop`, `office`, `reception`; adres türüne göre `presence.mix`; adres düzeyi lognormal çarpan `intensity_sigma`). Saat başına bulunamama olasılığı, hafta içi / Cumartesi ayrı. Alıcı yokluğu **durak düzeyinde** ve **varış saatine bağlıdır**: kapıda kimse yoksa duraktaki tüm gönderiler `recipient_absent` olur. `presence.enabled=false` → Faz 2 modeli (`outcome.p0`, gönderi düzeyi, saatten bağımsız). Profiller ayrı RNG akışıyla (`S_PRESENCE=5`) kurulur; dünyanın geri kalanını değiştirmez. Paylar ve profiller VARSAYIM'dır (gerçek veride başarısızlık saati/nedeni boş).

**Kayıt:** kol D'nin her denemesi (ertelenmemiş, teslim edilen ya da `recipient_absent`) `TimeRecord`'na yazılır; bilgiye bağlı başarısızlık bulunabilirliği sınamadığı için sayılmaz. Dışa: `delivery_log.json` (§1).

**Analiz (`cm_sim.delivery_time`):** gün tipi (hafta içi/Cumartesi) × 5 dilim. Tür şekli `q[tür, dilim]` = türdeki tüm adreslerin oranı (+1/+2); adresin genel oranı `p̄ = (bulunamadı + κa·q̄)/(deneme + κa)`; dilim tahmini `p[d] = (bulunamadı_d + κs·m_d)/(deneme_d + κs)`, `m_d = p̄·q[d]/q̄`. Bulgu türleri:
- `window`: kötü dilim (≥ `min_att_bad` deneme, ≥ `min_abs_bad` kendi "alıcı yok", tahmin ≥ `min_bad_rate`) ve önerilen dilim (≥ `min_att_good` deneme, kötüden en az `min_diff` iyi). Güven = P(p_kötü > p_iyi) (Beta sonsalları, nicelik integrali); `high` ≥ 0,95, `mid` ≥ 0,85, aksi `low`.
- `confirmation`: kötü dilim belli, başka dilimde kayıt yok, tahmin ≥ `confirm_bad_rate`; rotaya girmez, hasat sorusu olur.

Bulgu biçimi: `{type, bad, good|null, confidence|null, level, estimate[5], general, attempt[5], not_found[5], day_type}`; `proposal_text` → `"12–14: 0/10 teslim · 16–18: 4/4 teslim → 16–18 öner"`.

**Rotaya alma:** kurallı politika `fits_route(b, routing.time_min_confidence)` (varsayılan `mid`, yalnız `window`). Ajanda Orkestratör `apply_time_constraint {min_confidence, exclude[]}` ile karar verir (yoksa kurallı politika). Hasatla teyit edilen bulgu güvenden bağımsız girer (kötü dilim ≥ 0,8, söylenen "X'ten sonra" dilimi ≤ 0,05), reddedilen girmez.

**Zaman onarımı (`routing_memory.repair_times`):** pencere onarımından sonra. Amaç = sürüş dk + km × `time_km_cost_min` + Σ tahmini bulunamama(varış dilimi) × `time_revisit_min`. Adaylar: bulgu düğümünün tüm or-opt yerleri ve düğümü içeren tüm 2-opt ters çevirmeleri; en iyisi maliyeti ≥ `time_min_gain_min` düşürüyor ve bilinen pencere ihlalini artırmıyorsa uygulanır. Değişiklik: `{type: "time", address, move: move|reverse, old_order, new_order, old_arrival, new_arrival, extra_km, old_p, new_p, gain_min}`. **Sıra numaraları 1 tabanlı durak sırasıdır** (pencere değişikliklerinde de; Faz 2 metni bir fazla yazıyordu, düzeltildi).

**`compute_route` ek alanları:** `constraints[]` içinde `kind: "time_preference"` (`window` = önerilen dilim, `source = "Z<address>"`); `changes[]` içinde `type: "time"` + `label, finding (text), confirmed, old_slot, new_slot, text`; `comparison.no_time {km, planned_min, order, expected_absence} | null`; `memoryless/memory.expected_absence`; `diff.time_carried`, `diff.expected_absence` (`diff.carried` artık yalnız pencere taşıması); `time_findings[]` (aşağıdaki satır biçimi). Canlı seçim/teyit simülasyonun kurallı politikasıyla aynıysa `same_as_sim` (408/408).

**`delivery_time_analysis` çıktısı (araç, `GET /api/time/{gün}`):** `{gun, day_type, durak, window_finding, confirmation_pending, rule_policy, fits_route, bulgular[≤25], teyitler[≤10], yontem}` + API'de `selection{min_confidence, excluded, applied}`. Satır: `{address, label, address_type, type, day_type, bad_slot, good_slot, confidence, level, text, attempt[], not_found[], estimate[], confirmation, fits_route, cluster, courier, courier_name}`.

**`apply_time_constraint` çıktısı:** `{min_confidence, excluded, applied, cluster_count, rationale}`. Öneri (`proposal`/`plan`) ayrıca `time_constraints{min_confidence, excluded, applied} | null` taşır.

**`GET /api/time/{gün}/address/{adres}`:** `{address, day, history[{day, weekday, hour, slot, result: delivery|recipient_absent}], table{day_type, address_general_estimate, slots[{slot, attempt, delivery, not_found, estimate, type_mean}]}, finding|null, confirmation|null}`.

**`GET /api/time/example`:** `{app_data, example: meta.time_example, agent{finding, table, history}, route{change, same_as_sim, diff}, hidden_truth{profile, note}, summary: summary.time_analysis}`. `meta.time_example`: `{gun, weekday, kurye, courier_name, kume, adres, etiket, address_type, gecmis[], bulgu{…, bad_name, good_name, metin}, degisiklik, sonuc{zamansiz{varis, sonuc}, hafizali{varis, sonuc}}, not}`. Seçim kuralı: zaman onarımının taşıdığı, zamansız yürütmede `recipient_absent` / zaman-farkında teslim, ≥ 6 geçmiş deneme, demo gününe en yakın. **Seçilmiş örnektir**; büyüklük `summary.time_analysis`.

**`summary.time_analysis`:** `{gun, gunluk{bulgu, teyit, uygun, rotada, tasinan, dogru, expected_before, expected_after}, dogruluk, counterfactual_daily.{zamansiz, hafizali}.{fail, recipient_absent, revisit, km, minutes, preventable_fail, overtime_min}, diff_daily{… hafizali − zamansiz}, carried_stops{durak, fails_no_time, fails_memory, rota}, not}`. `accuracy`: rotaya alınan bulgularda gizli gerçek bulunamama farkı (kötü − önerilen dilim ortası) ≥ 0,10 olanların payı.

**Hasat (saat teyidi):** araç `time_confirmations {max_count}` → `{day, candidates[{address, label, address_type, type, bad_slot, evidence, estimate_bad, ask_courier, ask_courier_name, today_outgoing}], total}`; `save_questions` `reason` enum'una `time` eklendi (`hypothesis_type: null`); kurallı yedek günde en çok 5 saat sorusu. Cevap Hafıza Ajanı'na gitmez; `parse_confirmation` → `TimeSource.write_confirmation` (metin `redact` ile ayıklanır). Simülasyon (kol D) saat teyidini modellemez.

## 8. Faz 2c: onarım rotayı uzatmaz (sert kısıt) ve kaydırılamayan bulgu

**Kural (sahibin):** "Ajan mevcut rotadan daha uzun bir rota çıkarmamalı." Hafıza onarımları (öğle penceresi taşıması, teslim zamanı taşıması) **sert kısıtla** çalışır; beklenen başarısızlığın maliyeti fazla mesaiyi "kazanç" diye satın alamaz. Kısıtı bozan hamle, amaç fonksiyonundaki değerinden bağımsız reddedilir.

**`RepairLimits` (`cm_sim.routing_memory`; `plan_route(..., limits=)`):** `{max_extra_min, max_extra_km, band_max, wait_max, blocked_diff}`. Kol D `engine.repair_limits(cfg)`, ajan `agents.route.repair_limits(rc)` ile aynı değerlerden kurar. `limits=None` → kısıtsız (Faz 2b davranışı; yalnız testler ve ablasyonun `unconstrained` varyantı).
- **Beklenen rota süresi** (planlanan dk) = sürüş (km × `minutes_per_km`) + servis (taban + bilinen ek süre) + bilinen öğle penceresine düşen varışlarda bekleme `min(pencere sonu + pay − beklenen varış, quirks.lunch_wait_max)`, pencere `[başlangıç − pay, bitiş + pay)`, pay = `routing.repair_wait_margin_min` (30 dk; beklenen varış belirsiz, gerçekleşen çoğunlukla geç: paysız tahmin beklemeyi küçük gösterip beklemeyi önleyen taşımayı reddederdi). Bant bu süreyle karşılaştırılır. `RepairLimits.wait_margin`.
- **Onarım öncesi rota** = erteleme sonrası, servis düzeltmeli düz sıra. Servis düzeltmesi sırayı değiştirmez, iki tarafta da aynıdır.
- **Pencere onarımı:** aday, onarım öncesine göre `süre ≤ sınır` ve `km ≤ km₀ + max_extra_km` sağlamalı (taşıma ancak eklediği sürüş kaçırdığı beklemeden az ise kabul).
- **Zaman onarımı:** taban = pencere onarımı **sonrası** rota (zaman-farkında ≤ zamansız ≤ onarım öncesi) ve **km toleransı 0** (`replace(limits, max_extra_km=0)`): zaman hamlesi sürüşü yalnız tahmini bekleme kazancıyla satın alamaz; km toleransı yalnız öğle beklemesini kısaltan pencere taşımasınındır. Zaman onarımında ve aktarmada öğle penceresi ihlali de aynı geniş payla (`max(window_margin_min, repair_wait_margin_min)`) sayılır: zaman onarımı bilinen öğle durağını pencerenin yakınına sokamaz. Ayrıca her bulgu durağının yeni beklenen varışı `≤ max(vardiya bitişi, onarım girişindeki varışı)`; vardiya bitişi = `planning.start_minute + planning.band[1]` (09:00 + 528 = 17:48).
- **Sınır:** `sinir = min(süre₀ + max_extra_min, band_max)` eğer `süre₀ ≤ band_max`; aksi hâlde `sinir = süre₀` (bant zaten aşılıyorsa tolerans da yok).
- Config (`routing`): `repair_limits: true`, `repair_max_extra_min: 0`, `repair_max_extra_km: 0.5` (pencere + zaman birlikte, onarım öncesine göre), `repair_wait_margin_min: 30`, `time_blocked_diff: 0.3`, `time_alternatives: true`.

**`plan_route` yeni çıktıları:** `limits {before_min, after_min, before_km, after_km, border_min, tolerance_min, tolerance_km, band_min} | null`; `changes[].extra_min` (hamlenin beklenen süre farkı; tek hamle önceki hamlenin kazancını kullanabilir, toplam sınırı aşmaz); `time_blocked [{address, arrival, p_now, p_best, good, reason, min_extra_min, min_extra_km}]`; `ctx {addrs, xy, svc, depot, windows, presence}` (alternatif hesabı için rota bağlamı).
- **Kaydırılamadı:** onarımdan sonra varış dilimindeki tahmini bulunamama, bulgunun en iyi diliminden ≥ `time_blocked_diff` yüksek. `reason` (or-opt teşhisi): `no_good_hour` (rota uygun dilimde uğramıyor), `after_shift` (uygun dilim vardiya bitişinden sonra), `route_duration`, `band`, `km`, `window` (uygun yere taşımak bu kısıtı bozardı), `gain_insufficient`. `min_extra_min`: uygun dilime taşımanın en az ek süresi.

**`time_alternatives(routes, *, road_factor, mpk, start, scale, margin, limits, min_gain)`** (simülatör ve ajan AYNI fonksiyon; `routes`: rota anahtarı → `plan_route` çıktısı). Rota anahtarı ve rota sırasıyla, her kaydırılamayan bulgu için:
1. aynı rota (onarım zaten denedi; `reason` yazılır);
2. **aktarma** (`option: "transfer"`): bölgeden (≤ 3 km yol) geçen başka bir rotanın her konumu denenir. Kabul: iki rotanın toplam beklenen süresi en çok `max_extra_min` artar ve toplam km hiç artmaz, hedef rota bandı aşmaz (onarım öncesi bandı aşan rota hedef olamaz), durak hedefte vardiya bitişinden önce ve kendi bilinen penceresi dışında, iki rotada pencere ihlali artmaz, durağın tahmini bulunamaması ≥ `blocked_diff` düşer, toplam beklenen bulunamama ≥ `min_gain` (= `time_min_gain_min / time_revisit_min` durak) düşer. En çok kazanç, eşitlikte en az km. Kabul edilen aktarma sonraki aramalara işlenir (öneriler birlikte uygulanabilir);
3. aktarma yoksa uygun dilim vardiya içinde başlıyorsa `next_day`, değilse `evening_delivery_point`.
Satır: `{address, source, reason, arrival, p_now, good, good_slot, min_extra_min, sms: true, decision: "manager", option, target|null, target_order, target_arrival, target_p, extra_min_total, extra_km_total, target_duration_after, source_duration_after, gain_stop}`; dışa aktarım ve ajan ayrıca `{courier, courier_name, target_courier, target_courier_name, label, text, sms_text}` ekler (`delivery_time.alternative_text`, `sms_text`; SMS metni kişisel bilgi içermez). **Öneriler müdür kararıdır; simülasyon (kol D) uygulamaz, ölçülen etkide yoktur.**

**Ajan:** `RoutePlanner.limits`; `plan()` → `time_unshiftable[{…time_blocked, etiket, good_slot, metin}]`, `comparison.route_constraint` (= `limits`), `comparison.diff.time_unshiftable`; değişiklik metinleri "rota süresi ±X dk" içerir. `RoutePlanner.day_alternatives(day, mapping)`. Orkestratör aracı **`time_alternatives {}`** → `{gun, kaydirilamayan, aktarma, next_day, evening_delivery_point, oneriler[≤10], kisit{tolerance_min, tolerance_km, band_min, shift_end}, kural}`; sıra `delivery_time_analysis → apply_time_constraint → time_alternatives → compute_route`. Kurallı yedek aynı araçları aynı sırada çağırır, kuralı bir `decision` cümlesiyle söyler; öneri `time_alternatives[{address, label, courier, courier_name, option, reason, target_courier, target_courier_name, text, sms_text}] | null` taşır, riskler "… kısıt yüzünden aynı rotada kaydırılamadı …" satırını içerir.

**API (yeni alanlar, mevcutlar korunur):** `GET /api/time/example` → `constraint` (= `summary.time_analysis.constraint`), `example_constraint` (= `meta.time_example_constraint`), `example.route {limits, planned_min{zamansiz, hafizali}, km{…}, actual_min{…}, overtime_min{…}, shift_end, band_min}`. Yeni `GET /api/time/{gün}/alternatives` (= Orkestratör aracı çıktısı). `GET /api/route/{gün}/{kurye}` → `time_unshiftable[]`, `comparison.route_constraint`, `comparison.diff.time_unshiftable`.

**Çalıştırma klasörü:** snapshot `plan.limits`, `plan.time_blocked`; `time.json.alternatives {gün: [satır]}`; `meta.time_example` seçimi artık (aynı rota içinde) zıtlık → rota süresi artmamış ve gerçekleşen rota ≤ bant ve yeni varış ≤ vardiya bitişi → yeni dilim = bulgunun önerdiği dilim → sabah/öğle → öğleden sonra → geçmiş ≥ 6 → demo gününe yakınlık; `example.route` eklendi. Yeni `meta.time_example_constraint` (= alternatif satırı + `{day, weekday, address_type, finding, history, note}`; aktarma > ertesi gün > akşam, geçmiş ≥ 4, demo gününe yakın). `summary.arms.*.route_minutes_per_day`. `summary.time_analysis` yeni: `constraint {shortfall, tolerance_min, tolerance_km, band_min, route, violation, new_over_band, max_duration_diff_min, max_km_diff, mean_duration_diff_min}`, `overtime_route {route, remaining, max_increase_min}` (gerçekleşen; plan dışı yürütme oynaklığı tek rotada artış gösterebilir), `alternatives {total, reason{}, option{}, transfer_expected_gain_stop}`, `counterfactual_daily.*.{planned_min, expected_duration_min}`, `diff_daily.{planned_min, expected_duration_min}`, `daily.{unshiftable, transfer, next_day, evening_delivery_point, transfer_gain}`.

**Ablasyon:** yeni varyantlar `full_tol5`/`no_time_tol5` (`repair_max_extra_min=5`, duyarlılık), `unconstrained`/`no_time_unconstrained` (`repair_limits=false`, Faz 2b). `time_contribution` çiftleri `g20, g60, tol5, unconstrained_2_b`; sütunlar ek olarak `route_min_D` ve aynı rota karşı-olgusu `ayni_rota_{recipient_absent, revisit, km, mins, planned_min, expected_min, overtime_min}`; varyant satırlarında `constraint_violation, constraint_max_min, constraint_max_km, unshiftable_day, transfer_day`. `tam − zamansız` iki ayrı dünyadır (gürültülü); sıkı ölçü `ayni_rota_*`.

**Kabul testleri:** `sim/tests/test_repair_limits.py`, `agents/tests/test_phase2_c.py`, `api/tests/test_phase2_c_api.py`; 408/408 birebir (`agents/tests/test_phase2_b.py`, yavaş) korunur.

## 9. Faz 3: hikaye arayüzü (`ui-story/`, `/story/`)

**Sunum:** `GET /` → `307 /story/` (`ui-story/index.html` yoksa eski tek sayfa). Eski tek sayfa `GET /legacy` (`ui/index.html`; varlıkları `/ui/*`). Spec: `.kiro/specs/api-arayuz/` Gereksinim 7.

**Sahne → uç nokta:**

| Sahne | Çağrılar (sırayla) |
|---|---|
| 1 Sorun ve ilke | adım 0–5 yok (`data/scene1.json`, gerçek veri istisnası); adım 6 `GET /api/summary` (`long_term.summary.arms.*.unfamiliar_share`) |
| 2 Sabah | `GET /api/status` → `POST /api/memory/reset {day: 32}` → `POST /api/orchestrator/start {day: 32}` → `GET /api/orchestrator/session/{id}/stream?tempo_ms=0` (SSE; hata → `GET …/session/{id}?after=n` poll; API yok → `data/trace_fallback.json`) |
| 3 Onay | `GET /api/orchestrator/session/{id}` (Sahne 2'nin koşusu; `awaiting_approval` değilse) `POST /api/orchestrator/plan {day: 32}` → `POST …/session/{id}/ask {soru}` → `POST …/session/{id}/decision {karar: "approval"}` → `GET …/session/{id}?after={total_event}` (insan kararı + kapanış olayları); son adım (Faz 5): `GET /api/morning/{gün}` → `POST /api/morning/scan` (örnek gönderiler + bir istisna) |
| 4 Kapıda | `GET /api/briefing/32/O02`, `GET /api/route/32/O02` (durak sırası = `comparison.memory.order`, varış = `expected_arrival`), `POST /api/memory/feedback {day, record, valid}`, `POST /api/note {day, courier, text, lat, lng, minute}`, `GET /api/briefing/{demo.next.day}/{demo.next.courier}`, `GET /api/meta` (`critical.memory_gain`), `GET /api/summary` (`summary.memory_routing.type`), `GET /api/speech?text=` (501 → tarayıcı sesi) |
| 5 Hasat | `POST /api/harvest/plan {day: 32}` → (soru `demo.harvest_gap.address` / `demo.harvest_time.address` ile bulunur, kimlikle değil) `GET /api/route/32/{courier}` (önce) → `POST /api/harvest/simulate-answer {question_id}` → `GET /api/route/32/{courier}` (sonra); `GET /api/time/example` |
| 6 Öğrenme | `GET /api/learning`, `GET /api/summary` (`daily.{A,B,C,D}[].{day, first_attempt_rate}`, `summary.arms.*.{label, first_attempt_rate, fail_by_reason}`, `summary.preventable_reasons`, `sweep.rows[].arms.*.first_attempt_rate`, `sweep.headline`, `calibration.{source, rows[].{measure, explanation, value, compatible}}`, `ablation.variants`) |
| 7 Değer | `GET /api/economics` (`headline`, `operation.{waterfall, arms, scale}`, `scale`, `model_comparison`, `llm_scenarios`, `llm.agents`, `models`, `assumptions`), `GET /api/economics?scenario=optimize`, `GET /api/economics?model_assignment=&model_memory=&model_briefing=&cache=` (model seçici), `GET /api/economics?courier_daily_cost_tl=&fails_other_tl=&second_attempt_min=&km_cost_tl=` (kaydırıcılar), `GET /api/summary` (`long_term.summary.arms.*.unfamiliar_share`) |
| 8 Kapanış | `GET /api/status` (`mode`, `models`), `GET /api/economics` (`headline`) |

**Kayıtlı yanıtlar (`ui-story/data/fallback.json`, `tools/record_fallback.py`):** düz JSON nesnesi; anahtar `"GET <path+sorgu>"` ya da `"POST <path>#<name>"` (aynı yola farklı gövdeli POST'lar: `ask#onur|gokhan`, `decision#approval`, `note#personal|noise|back`, `geri-bildirim#<kayıt>`, `simule-cevap#<question_id>`; aynı GET'in farklı anı: `route/32/<courier>#before|after-<question_id>`). `GET /api/summary` kırpılmış hâlde saklanır (arayüzün okuduğu alanlar). Ek anahtarlar:
- `demo`: `{note_address, note_order, next{day, courier, name}, harvest_gap{address, courier, courier_name}, harvest_time{address, courier, courier_name}}`. Kurallar (aracın docstring'i): not adresi O02'nin gün 32 rotasında, bölgeye yabancı, kapı notu yok, 8–20. sıra, sonraki 7 günde başka kuryenin gittiği; en erken gün, sonra en küçük sıra. Hasat: boşluk sorusu O02 rotasında ve simüle cevabı hafızaya yazılıp rotayı değiştiren ilki; saat teyidi cevabı `confirmation` olup o adrese bugün giden kuryenin rotasını değiştiren ilki.
- `_note`: üretim notu.

Kayıt mock modda, temiz sunucuyla alınır; araç önce ve sonra `POST /api/memory/reset` çağırır. Arayüz ağ hatasında kayda düşer ve oturum boyunca öyle kalır (`?record` ile zorlanabilir, `?api=<address>` ile başka sunucu). Kayıtta olmayan istek (serbest soru, serbest not, kaydırıcı, model seçici) açık bir uyarıyla reddedilir. Veri yeniden üretilince yedekler de yeniden kaydedilir (`docs/veri-haritasi.md`).

## 10. Faz 5: sabah (şubeden çıkış; ayrıştırma indirme okutmasında)

Spec: `.kiro/specs/sabah-akisi/`. Süreler saha bilgisidir (VARSAYIM).

**Config `morning`:** `{enabled, current_min: 90, presorted_min: 30, deviation_min: 10, presorted_arms: [D]}`. Çıkış = `planning.start_minute` + kolun sabah süresi + kurye sapması (`rng.S_MORNING = 22`; normal σ = `deviation_min`, ±2σ; kollar arası ortak). `enabled: false` → Faz 0–4 (çıkış = mesai başı).

**Simülatör çıktıları:** günlük `overtime_minutes` = Σ max(0, dönüş − vardiya bitişi), vardiya bitişi = mesai başı + `band[1]` (17:48); `departure_mean`, `end_mean` (gece yarısından dk). `summary.arms.*.{departure_mean, end_mean}`. Anlık görüntü rotası `departure`; kol D `counterfactual.current_morning` (`_route_summary` + `start`, `end`). `summary.morning = {shortfall, shift_start, shift_end, current_min, presorted_min, deviation_min, presorted_arms, arms.{A..D}.{departure_mean, return_mean}, counterfactual: {day, daily.{memory, current_morning}.{fail, preventable_fail, recipient_absent, revisit, minutes, ok, overtime_min, departure_mean, return_mean, after_shift_returning_share}, diff_daily}, note}`. `RepairLimits.shift_end_at`: Faz 2c'nin vardiya bitişi saat olarak sabit.

**Deneyler:** tarama (`sweep.yaml → fixed`), öğrenme ve ablasyonun hafıza varyantları `morning.presorted_arms=[]`; ablasyon `full_morning` + `time_contribution.morning = full_morning − tam` (ek anahtarlar `departure_D`, `return_D`).

**Ajan:** `agents.route.morning_info(cfg)`, `plan_departure(sb, arm)`; `RoutePlanner.rc["start"]` = planın çıkışı; `compute_route` → `start` (çıkış), `start_min`, `estimated_return`. Orkestratör aracı **`sorting_plan {}`** → `{day, shortfall, shelf_count, shipment, next_day_shelf, shelves[{shelf, cluster, courier, name, stop, shipment, first_loaded, last_loaded}], departure{shift_start, today, presorted, gain_min}, rule, source}`; kurallı sıra `… compute_route → sorting_plan → present_proposal`; öneri `morning{shelf_count, shipment, next_day_shelf, departure, shelves[{shelf, cluster, courier, name, shipment}]} | null`.

**API:** `GET /api/morning/{gün}` → `{day, plan_source, plan (sorting_plan), departures[{cluster, courier, name, departure, return_time, departure_current, return_current}], summary (summary.morning), example_shipments[]}`. `POST /api/morning/scan {day, shipment}` → `{shipment, exception, shelf, cluster, courier, name, stop_order, load_order, stop, label, instruction, plan_source}`; bugün kapalı bilinen adres → `shelf: "next_day"`, planda yok → `shelf: "flexible"` (`exception: true`). Gönderi kimliği uygulamanın ürettiği biçimde: `G<gün>-<adres>-<sıra>`.

**Koordinat hassasiyeti:** anlık görüntü durakları, depo ve `addresses` 7 ondalık (`export.ND_COORD`, ~1 cm); ajan rotayı bunlardan yeniden kurar. Onarım seçimlerinde eşitlik toleranslıdır (km 1e-4, dk 1e-3; sonra en küçük konum).

**Zaman onarımı (düzeltme):** `routing_memory.repair_times` adayı, hamle sahibinin (bulgu düğümü) bulunamama olasılığını düşürmüyorsa eler. Faz 5 verisinde 20 günde 31 zaman hamlesinin 2'si, başka bir düğüm ya da yol için yapılan ters çevirmeyle sahibini kötü saate itiyordu (müdüre "09–12 öner → 16:47" gibi çelişkili satır). Simülatör ve ajan aynı fonksiyonu kullanır; `changes[type=time]` her zaman `new_p < old_p`.

**Ekonomi:** `D_current` = kol D, başarısız ve fazla mesai `counterfactual` farkıyla bugünkü sabaha çevrilmiş. Şelale `hafiza = D_current − C`, yeni `sabah = D − D_current` (kod `morning`). `gain.vs_C` yalnız hafıza (`ref = D_current`); `gain` yalnız `vs_C`, `vs_B`. Üst düzey `morning{departure_current_min, departure_presorted_min, overtime_min_day, fails_per_day, tl_day, tl_year, overtime_tl_day, fails_tl_day, gain, note}` (`gain` = `vs_C` biçiminde, D ← aynı rota bugünkü sabahla).

## 11. Faz 2d: bilgi türleri, durak kartları, yaklaşma tetiği

**Hafıza türleri.** `agents.rundata.MEMORY_KINDS = QUIRK_KINDS + INFO_KINDS`. `INFO_KINDS = (park, building_access, directions, animal, other_info)` yalnız bilgi taşır: simülatörde karşılığı yoktur, `MemoryConstraints` bunları okumaz (plan, rota, ETA ve simülasyonla eşitlik değişmez). `MemoryBook.upsert`: bilgi türünde metin zorunludur (kalıp cümle yok); metin kapı/bina şifresi ya da giriş kodu içeriyorsa `MemoryWriteError` (`guardrails.find_secret`). Hafıza Ajanı araç şemaları (`write_memory.type`, `report_result.type`) `MEMORY_KINDS` enum'unu kullanır. Kurallı yedek (`memory.classify`): rotayı etkileyen türler önceliklidir, bilgi türü yalnız anahtar kelime sayısı açıkça fazlaysa kazanır (simülatör notlarının sınıflandırması değişmez, test); bilgi türünün ipucu metni notun kendisidir (`info_text`: kişisel veri ve şifre ayıklanır, tek cümle, ≤ 140 karakter). Hasat hipotez türleri `QUIRK_KINDS` olarak kalır.

**Kart** (`agents.cards.card_of`): `{id, type, title, text, moment: approaching|at_door, info_kind, affects_route, source_count, confidence: confirmed|single_source|needs_confirmation, confirmation_reason, first_day, last_day, confirmed_day, temporary, valid_until, window, source_list[]}`. `moment`: `park, directions, position_wrong, roadwork, back_entry` → `approaching` (araç durmadan lazım), diğerleri `at_door`. `confidence`: Değerlendirme Ajanı teyide aldıysa `needs_confirmation`; ≥ 2 kaynak ya da kurye teyidi → `confirmed`. Kartlar brifingle aynı süzgeçten geçer (`hint_today_valid`). Durak içi sıra: yaklaşırken → rotayı etkileyen → çok kaynaklı.

**`GET /api/cards/{day}/{courier}`** → `{day, weekday, courier, name, plan_source, stop, stops_with_cards, card, type_distribution{}, approach_m, door_m, stops[{order, address, label, lat, lng, expected_arrival, unfamiliar, shipment, cards[]}]}`. Rota onaylı plandan (yoksa simülasyon planı), hafızalı sırayla; `all=false` yalnız kartlı durakları döndürür.

**`POST /api/approach`** (durumsuz; LLM yok) → `{day, courier, stop{order, address, label, lat, lng, expected_arrival, unfamiliar, distance_m}|null, moment|null, cards[≤ 2], to_speak|null, pending}`. `next_order` verilirse yalnız o durak, verilmezse `APPROACH_M` (400 m) içindeki en yakın kartlı durak. Mesafe ≤ `DOOR_M` (60 m) → `at_door`: kapı kartları + söylenmemiş yaklaşırken kartları; ≤ 400 m → `approaching`; daha uzak → kart yok, `pending` sayısı. `shown` içindeki kart kimlikleri tekrar söylenmez; bir tetikte en çok 2 kart (`SPEAK_MAX`, sürüş güvenliği). `to_speak` = kart metinleri birleşik (`/api/speech` ile okunabilir).

**Kabul testleri:** `agents/tests/test_cards.py` (5), `api/tests/test_cards_api.py` (2).

## 12. Değerlendirme Ajanı, Bölge Ajanı, ajan akışı

**Ajan akışı** (`agents.feed.AgentFeed`, dosya `agent_feed.json` hafıza dosyasının yanında): olay `{n, time, day, agent, type, summary, status, …ayrıntı}`. `agent: memory | review | region | manager`; `status: applied | awaiting_approval | approved | rejected | undone | info`. Not metninin kendisi yazılmaz; Hafıza Ajanı'nın ayıklanmış sonucu yazılır (`POST /api/note`, `POST /api/memory/feedback` akışa ekler).

**Değerlendirme Ajanı** (`agents.review.ReviewStore.morning_review(day)`, LLM ajanı `review`, istem `prompts/review.md`): son `WINDOW_DAYS` (5) gün ↔ önceki 5 gün. Araçlar `trend, hint_outcomes, recurring_problems, duration_estimate, assignment_check, apply`; bitiş `present_report {summary, going_well[], going_badly[]}`. Eylemler `drop_record | flag_for_confirmation | open_question | parameter | proposal`. Korkuluklar araçta: düşürme yalnız tek kaynaklı + ≥ 2 çelişkide (yoksa teyide alınır); parametreler `PARAM_LIMITS` içinde; atama yalnız öneri (müdür onayı); günde en çok `AUTO_MAX` (12) otomatik eylem. Her eylem akışa yazılır; `undoable` olanlar `decision: undo` ile geri alınır (`MemoryBook.undo`). Kuryeyi değil sistemin kararını değerlendirir. Yanıt `{day, mode, degraded, report, params, question_queue[], trace[]}`.

**Bölge Ajanı** (`agents.region.RegionStats` hesap, `agents.region_agent.RegionAgent`, LLM ajanı `region`, istem `prompts/region.md`): ~300 m blok; zorluk endeksi = bloğun bilgi nedenli başarısız oranı (büzülmüş, `PRIOR` = 20 deneme) ÷ şube ortalaması; ≥ 1,5 `high`, ≥ 1,1 `mid`. Hafıza boşluğu = zor blok + kayıt yok. İki görev: `cluster_card` (araçlar `branch_summary, hard_blocks, cluster_summary`; bitiş `present_cluster_card {sentences[≤ 4], difficulty_note}`) ve `branch` (araçlar `branch_summary, hard_blocks, open_question`; bitiş `present_branch_report {summary[≤ 4], priority_blocks[]}`). `open_question` yalnız boşluklu zor bloğa, günde ≤ `QUESTION_MAX` (5), aynı blok aynı gün bir kez; sorular akışa ve Değerlendirme Ajanı'nın `question_queue`'suna yazılır. Canlı yol tamamlanamazsa kurallı yedek aynı araçlarla sürer (`degraded: true`).

**Kabul testleri:** `agents/tests/test_review.py` (4), `agents/tests/test_region_agent.py` (5; sahte LLM ile canlı döngü), `api/tests/test_review_region_api.py` (3).

## 13. Gerçek gün (Beykoz 5 Mayıs)

**Dosya** `data/real_day/2026-05-05.json`: `{day, previous_day, weekday, depot, band, source, zones[{name, rings, courier}], couriers[{id, name, zone, stop, shipment, mins, return_time}], clusters[{id, courier, name, stop, shipment, mins, km, return_time, unfamiliar, rings, at, seq}], stop_fields, stops[], rates{fail_familiar, fail_unfamiliar, source}, summary{}, memory{source, day, records{durak: [kayıt]}, quirky[], note}}`. `stop_fields = [lat, lng, shipment, zone, cluster, unfamiliar, unfamiliar_by_zone, no_zone_in_fixed]`. Bölge kodu ve kurye kimliği yok; kurye adları takma ad. `memory.quirky` simülasyonun gizli gerçeğidir, yalnız kapsam ölçümü içindir (ajan görmez).

**Servis** (`agents.real_day.RealDay`): `memory_summary()` (kapsam + beklenen başarısız: gönderi × gerçek oranlar; yabancıdaki fazla başarısızlık bilgi gerektiren durakların hafızada kapsanan payı kadar kapanır, VARSAYIM), `cluster(cid)` (motor sırası `agents.stop_order.route_order`, kartlar, yol: `data/map/osrm_real.json` bacak önbelleği, önbellekte olmayan bacak düz), `transfer()` (komşu şubeye bir kurye; yeniden dengeleme YAKLAŞIK, etiketli). Gerçek duraklar simülasyon adreslerine 15 m içinde eşlenir; varsayılan soyut dünyada eşleşme olmadığından kartlar yalnız dosyadaki geçmişten gelir.
