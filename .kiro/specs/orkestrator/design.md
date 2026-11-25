# Tasarım: Orkestratör Ajanı

## Modüller

| Dosya | İçerik |
|---|---|
| `agents/trace.py` | `Trace`: sıralı olay kaydı, `emit(type, **fields)`, `since(n)`, dinleyici (SSE için). `source` varsayılanı `trace.source`. Olay tipleri: `start, decision, tool, result, error, fallback, proposal, awaiting_approval, human_decision, response, done` |
| `agents/route.py` | `RouteConstraint` (yapılı hafıza kısıtı), `ConstraintSource` protokolü, `NoConstraints`, `MemoryConstraints(book, run)`, `EtaModel`, `RoutePlanner(run, source).plan(gün, küme, kurye, expected_min, hafıza_sayacı)` ve `apply()`; `cm_sim.routing_memory.plan_route`'u çağırır (tek fonksiyon, iki kullanıcı: kol D ve bu araç) |
| `agents/orchestrator.py` | `DayTools` (deterministik araçlar), `diff(a, b)`, `Orchestrator.plan / ask / apply_decision`, `Session`, `SessionStore` |
| `agents/prompts/orchestrator.md` | Türkçe sistem istemi: sıra, açık kadar ödünç, sayı uydurma yok, iki seçenekli senaryo cevabı |
| `agents/llm.py` | `run_agent(..., on_text=)`: modelin metin blokları `decision` olayına gider |
| `agents/__init__.py` | `Services.orchestrator`, `Services.sessions`; model `CM_MODEL_ORCHESTRATOR` |
| `api/main.py` | `/api/orchestrator/*`, `/api/plan/{day}` |

## Veri modeli

- **Yerel kadro:** atama girdisindeki (`assign/D/<gün>.json`) `borrowed` olmayan müsait kuryeler.
- **Komşu şube aday havuzu:** aynı dosyadaki `borrowed` kuryeler (senaryo `borrowed_courier.yaml` komşu şubenin o gün verebileceği adayları getirir). Orkestratör kaç tanesini alacağına kendisi karar verir.
- **Kümeler:** dinamik planlama motorunun (simülatör D kolu) günün kümeleri; küme sayısı hacimden gelir (`n_clusters`). Rota id = küme id.

## Hesaplar

- Maliyet = atama matrisindeki `cost` (`w_fail × exp_fail + w_time × exp_min`, `estimation.expected_cost`).
- Kurye < küme → `linear_sum_assignment` dikdörtgen çözer; kalan küme(ler) merkezine en yakın 2 atanmış kümeye eşit bölünür: süre, başarısız, yabancı durak payla eklenir (yaklaşık, `dispatch_note`).
- `EtaModel`: `gerçekleşen ≈ a × planlanan + b × (exp_min − (service_per_stop × durak + service_per_shipment × gönderi))`, önceki değerlendirme günlerine en küçük kareler. Demo gününde (32) 234 geçmiş rotayla a=0,86, b=1,01, ortalama mutlak hata ~30 dk (planlanan süreyle ~85 dk).
- Aday sıralama: her aday için `yerel + mevcut ödünç + aday` ile Hungarian → toplam maliyet; açgözlü seçim.
- Senaryo skoru: `w_fail × expected_fails + w_time × over_band_min` (ağırlıklar `config.yaml → assignment`).

## Akış

```
plan(gün):
  basla → karar → read_volume → karar → capacity_gap
  açık>0 ve aday var: karar → neighbor_candidates(need=açık) → karar
  → core_assignment(borrowed=önerilen)
  ödünç/yeni varsa: karar → compute_route ×(≤3)
  karar → arac:present_proposal → oneri → escalation()
    acil durum yok:  auto_decision → bitti(finalized)          (temassız, kaynak kural)
    acil durum var:  escalation{reasons} → awaiting_approval   (capacity | overtime | plan_worse | manual)
decision(onay|ret|duzenle) → human_decision → bitti            (yalnız eskalasyonda)
ask(soru): basla → karar → [neighbor_candidates → core_assignment] → core_assignment → arac:yanitla → yanit
```

Canlı yolda araç sarmalayıcıları `tool`/`result` olaylarını yazar; `run_agent(on_text)` modelin açıklama cümlelerini `decision` olarak yazar. Kurallı yedek aynı sarmalayıcıları çağırır. Bu yüzden izin biçimi iki yolda aynıdır; test `test_live_path_produces_same_trace_format` mock izinden kurulan sahte canlı yanıtlarla bunu doğrular.

## Hafıza-farkında rota (uygulandı)

`RoutePlanner(run, source=MemoryConstraints(book, run))`: `constraints(gün, adresler)` hafıza kayıtlarından `RouteConstraint` üretir (kısıt eşlemesi: `docs/sozlesmeler.md` §6); `apply()`:
- **Planda erteleme:** kapalı gün/geçici kapalı durağı, kayıt en az `routing.defer_min_sources` (2) bağımsız kaynaklıysa rotadan çıkarır (`changes[].type = deferred`); tek kaynaklıysa rotada kalır, brifingde "kapıda teyit edin".
- **Servis düzeltmesi:** `extra_service` kısıtı planlanan süreye ve `EtaModel`'e eklenir.
- **Pencere onarımı:** beklenen varışı öğle penceresine düşen durak en az km artışıyla taşınır (`type = window`, `old_order/new_order`, `extra_km`).
- Çıktıda `comparison` (hafızasız ↔ hafızalı sıra, fark, simülasyon karşı-olgusu) ve `same_as_sim` vardır. Araç ve iz biçimi değişmez.

**Kim gitsin:** adaylar sınır sokak tanıklığıyla (`border_side`) farklılaşır; `GET /api/orchestrator/candidates/{gün}` aynı çıktıyı LLM'siz verir. **Orkestratör planı = simülatör planı** korunur (`assign/D` matrisi hasattan önceki hafızayla yazılıdır).

## Teslim zamanı

Akış: `… core_assignment → delivery_time_analysis → apply_time_constraint → compute_route → present_proposal`. `DayTools` `TimeSource`'ndan (`agents/delivery_time.py`) bulguları alır; `apply_time_constraint` seçimi kaydeder, sonraki `compute_route` aynı seçimle `RoutePlanner(time="auto")` çağırır. Seçim, `TimeSource` üzerinde gün başına tutulur ve onaylı plana `time_constraints` olarak yazılır. Hasat'ta teyitlenen bulgu seçimden bağımsız girer. Araç ve iz biçimi değişmez (`istem: prompts/orchestrator.md`). Test: `agents/tests/test_delivery_time_agent.py`.

## Rota kısıtı ve alternatifler

Akış: `… apply_time_constraint → time_alternatives → compute_route → present_proposal`. `time_alternatives` girdisizdir; `DayTools` günün rotaları için `RoutePlanner.day_alternatives`'ni çağırır (simülatörle aynı fonksiyon) ve sonucu öneriye `time_alternatives` (ilk 10) olarak, riskler listesine tek cümleyle yazar. İlke: onarım rotayı uzatmaz, fazla mesai satın almaz; kaydırılamayan bulgu müdüre alternatif olur. Test: `agents/tests/test_repair_constraint.py`.

## Kayıt-oynat

Ajan adları: `orchestrator`, `ask_orchestrator` (Hasat Ajanı aynı iz biçimini ve araç sarmalayıcılarını kullanır; adı `harvest`). Kaset anahtarı isteğin tamamıdır (araç sonuçları dahil); araç sonuçları deterministik olduğu için kayıt aynı tıklama sırası ve sıfırlanmış hafızayla oynar (`python -m agents.record`).

**Temassız zincir (Gereksinim 6):** `Orchestrator.escalation(ar, proposal, manager_review)` saf ve deterministiktir; eşikler `ESCALATE_COURIER_OVER_MIN` (240) ve `ESCALATE_TOTAL_OVER_MIN` (1500) `agents/orchestrator.py` başındadır. Simülasyonun 20 değerlendirme gününde yalnız 22 ve 24 eskale olur; olağan yoğun gün (32) temassızdır. `SessionStore.start` hata yolunda `escalation{agent_failed}` yazar. Test: `agents/tests/test_orchestrator.py` (`test_touchless_without_emergency`, `test_escalates_only_in_emergency`).
