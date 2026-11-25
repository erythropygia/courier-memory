# Tasarım: Ajanlar

## Modüller (`agents/`)

| Dosya | İçerik |
|---|---|
| `llm.py` | `LLM`, `Tool`, `AgentRun`, `obj()` (strict şema yardımcısı), `AgentError`, `CassetteMiss` |
| `rundata.py` | `RunData`: meta, kuryeler, adresler (numpy), `snapshot(arm, gün)`, `assign_input(arm, gün)`, `memory_snapshot(gün)`, `notes()`, `notes_truth()`, `route_of(gün, kurye)`, `nearest(lat, lng, r)`. Ayrıca `parse_waybill`. |
| `memorybook.py` | `MemoryBook`: `reset(gün)`, `ensure(gün)`, `for_address`, `upsert(…, source="agent", window=None)` (kişisel veri ve uzunluk denetimi), `feedback`, `drop`, `summary`. Kayıtta `window` ve `source_list[]` alanları vardır. `CANON` sözlüğü tür başına nötr ipucu cümlesini tutar. |
| `guardrails.py` | `find_pii`, `redact` (regex) |
| `assignment.py` | `AssignmentTools` (deterministik), `AssignmentAgent.propose/ask` |
| `memory.py` | `MemoryTools`, `MemoryAgent.process(…, address_id=None, source="agent")`, anahtar kelime sınıflandırıcısı `classify` (mock), `parse_window` ("12 ile 1.5 arası" → `[720, 810]`) |
| `harvest.py` | `HarvestTools` (`memory_gaps`, `recurring_failure`, `save_questions`), `HarvestAgent.plan(gün, iz)`, `HarvestStore`, `SeniorSimulator` (demo: simüle cevap) |
| `briefing.py` | `BriefingTools.route_risks` (`hint_today_valid` süzmesi), `BriefingAgent(run, book, llm, plans=None).prepare` (onaylı plan, `compute_route`, `EtaModel`) |
| `tr.py` | `dative(n)` ("3'e", "6'ya"), `num()` (1.234,5), `hhmm()` |
| `prompts/*.md` | Türkçe sistem istemleri |
| `evaluate.py` | Hafıza Ajanı doğruluk ölçümü |
| `prompts/harvest.md` | Hasat Ajanı istemi: hangi boşluk, kime, hangi soru; hipotez teyitsiz yazılmaz |
| `delivery_time.py` | Faz 2b: `TimeData`, `TimeSource`, `time_source(run)`, `parse_confirmation`; `cm_sim.delivery_time` saf fonksiyonlarını çağırır |
| `__init__.py` | `Services.create(run_dir, mode, memory_file)`; `.harvest` = `HarvestStore` |

## Ajan döngüsü (`LLM.run_agent`)

Sözde kod:

```
messages = geçmiş + [user]
for tur in range(max_turns):
    req = {model, max_tokens: 16000, system: [{text, cache_control: ephemeral}], messages,
           output_config: {effort[, format: json_schema]}, tools: [strict]}
    resp = _call(ajan, req)            # live | record | replay
    refusal / max_tokens → AgentError
    pause_turn → assistant'ı ekle, devam et
    tool_use → her blok için:
        bitiş aracı → final_input al, "Kaydedildi." döndür, bitir
        araç → fn(girdi) → tool_result (hata → is_error)
        adimlar += {arac, girdi, ozet}
    end_turn → metin; output_schema varsa JSON; bitiş aracı gerekip çağrılmadıysa bir kez hatırlat
```

## Bozulmaya dayanıklılık

Her ajan metodu aynı kalıbı izler:

```
if llm.uses_llm:
    try: canlı yol → sonuç (degraded=False)
    except Exception as e: mock yol → sonuç (degraded=True, error=str(e))
else: mock yol
```

Mock yolu aynı deterministik araçları kullanır. Sayılar canlı yolla aynıdır; değişen yalnızca dildir.

## Hasat Ajanı akışı

```
plan(gün): basla → karar → arac:memory_gaps → sonuc → [arac:recurring_failure → sonuc]
             → karar → arac:save_questions → sonuc → arac:harvest_plan → bitti
```
- Kurye başına ≤ 3, şubede ≤ 30 soru; boşluk sorusu yalnız yerel çalışan kuryeye; hipotez teyitsiz yazılmaz.
- Cevap: `HarvestStore.reply` → `MemoryAgent.process(address_id=…, source="harvest")`. `simulate_answer` aynı yolu `SeniorSimulator` ile besler (`simulate: true`).
- İz biçimi Orkestratör ile aynıdır (`Trace`, araç sarmalayıcıları); mock ve canlı yol aynı olayları yazar.
- Brifing: `compute_route` (onaylı plan + `MemoryConstraints`) → hafızalı sıra, `EtaModel` dönüş saati, `route_changes`; ipuçları `hint_today_valid` ile güne/saate göre süzülür.

## Saat teyidi akışı (Faz 2b)

- Hasat'ta `time_confirmations` aday listesini verir (kötü dilim belli, başka veri yok); soru `reason: time`. Cevap `HarvestStore.reply` içinde `parse_confirmation` ile çözülür ve `TimeSource.write_confirmation`'a yazılır (Hafıza Ajanı'na gitmez). Evet: kötü dilim ≥ 0,8, söylenen "X'ten sonra" dilimi ≤ 0,05 olarak rotaya girer; hayır: girmez.
- Analiz yalnız `delivery_log.json` satırlarından, `day < hedef gün` ile yapılır.

## Rota kısıtı ve alternatifler (Faz 2c)

- `agents/route.py`: `repair_limits(rc)` config'ten `RepairLimits` kurar; `RoutePlanner.plan` `plan_route(..., limits=)` çağırır. Çıktıya `time_unshiftable[]`, `comparison.route_constraint{before_min, after_min, border_min, before_km, after_km, tolerance}`, `diff.time_unshiftable` eklenir.
- `RoutePlanner.day_alternatives(day, mapping)`: günün rotaları için `cm_sim.routing_memory.time_alternatives` (simülatörle aynı fonksiyon). Alternatif uygulanmaz; müdür kararı.

## Kayıt-oynat

- Anahtar: isteğin (model, sistem, araçlar, mesajlar, output_config) sıralı JSON'unun sha256'sı.
- Demo senaryosu sunumdan önce `record` modunda bir kez koşulur. `cassettes/` repoya girer.
- `replay`, aynı istekleri ağsız yanıtlar. Farklı bir soru gelirse mock yedeği devreye girer.
