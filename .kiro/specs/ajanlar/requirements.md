# Gereksinimler: Ajanlar (Atama, Hafıza, Brifing, Hasat)

## Giriş

Dört ajan Amazon Bedrock üzerinde Claude ile çalışır. Sözleşme ve veri biçimleri için `docs/sozlesmeler.md` §1, §3 ve §4 esas alınır.

Ajanlar yalnızca çalıştırma klasörünü (`data/demo_run/`) okur; simülatör koduna bağımlı değildir. AWS erişimi olmadan da her şey çalışır: `mock` modunda deterministik yedek yollar kullanılır. Etkinlik günü `CM_LLM_MODE=live` ile canlı moda geçilir.

## Gereksinimler

### Gereksinim 1: LLM katmanı ve modlar
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, canlı demo internet ya da kota sorunu yüzünden çökmesin istiyorum.

#### Kabul kriterleri
1. `CM_LLM_MODE` ortam değişkeni `mock | live | record | replay` değerlerinden birini almalıdır; varsayılan `mock`'tur.
2. Canlı çağrı `anthropic` SDK'sının `AnthropicBedrockMantle` istemcisiyle yapılmalıdır. Model `CM_MODEL_ID` (varsayılan `anthropic.claude-opus-5-5`), ajan başına `CM_MODEL_ASSIGNMENT` / `CM_MODEL_MEMORY` / `CM_MODEL_BRIEFING` / `CM_MODEL_ORCHESTRATOR` / `CM_MODEL_HARVEST` ile ezilebilir. `run_agent` isteğe bağlı `on_text` geri çağrısıyla modelin metin bloklarını iletir (ajan izi). Bölge `AWS_REGION`'dan gelir. `CM_BEDROCK_API_KEY` ya da `AWS_PROFILE` varsa kullanılmalıdır.
3. İstekler `tool_choice`, `thinking`, `temperature`, `top_p` ve `top_k` göndermemelidir. Araçlar `strict: true` olmalı, derinlik `output_config.effort` ile verilmelidir. Sistem istemi `cache_control: ephemeral` taşımalıdır.
4. `stop_reason` içerik okunmadan önce kontrol edilmelidir:
   - `refusal` ve `max_tokens` hata sayılır.
   - `pause_turn` ise döngü devam eder.
5. Araç hatası modele `is_error: true` ile geri verilmeli, döngü çökmemelidir.
6. `record` modunda her yanıt `cassettes/<agent>-<hash>.json` dosyasına yazılmalıdır. `replay` modunda aynı istek kayıttan dönmeli, kayıt yoksa ajan mock yedeğine düşmelidir.
7. Canlı ya da replay yolunda herhangi bir hata olursa ajan mock yedeğini kullanmalı ve sonuçta `degraded: true` ile `error` alanlarını döndürmelidir.

### Gereksinim 2: Atama Ajanı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, sabah atama önerisini gerekçesiyle görmek ve "ya şöyle olursa?" diye sorabilmek istiyorum.

#### Kabul kriterleri
1. Araçlar `assign/D/<gün>.json` matrisleri üzerinde deterministik çalışmalıdır:
   - `day_summary`
   - `cluster_detail(cluster_id)`
   - `courier_detail(courier_id)`
   - `solve_assignment(exclude[], pin[{cluster_id, courier_id}])`: Hungarian çözümü; önceki atamaya göre farkı da döndürür.
2. Öneri akışı `save_assignment(assignment, rationale[], highlights[])` bitiş aracıyla bitmelidir. Atama doğrulanmalıdır: tüm kümeler kapsanır, kurye tekrarlanmaz, yalnız müsait kuryeler kullanılır.
3. Soru akışı `respond(response, assignment[])` ile bitmelidir. Önceki konuşma geçmişi ve onaylanmış atama bağlamda yer almalıdır.
4. Sonuç §4'teki "Atama sonucu" biçimindedir. `comparison.history_blind_expected_fails` değeri, küme başına kurye ortalamalarının toplamıdır.
5. Mock yolu:
   - Aynı araçlarla şablon gerekçe üretir.
   - Senaryo sorularında metinden kurye adı/kimliği ile "yerine", "yedek", "gelmezse" kalıplarını çıkarır.
6. Dil `sunum-dili.md`'ye uymalıdır: "performans puanı" yok, kurye sıralaması yok, öneri dili kullanılır.

### Gereksinim 3: Hafıza Ajanı
**Kullanıcı hikayesi:** Bir kurye olarak, 3 saniyelik notumun doğru adrese bağlanmasını ve kişisel bilgilerin kaydedilmemesini istiyorum.

#### Kabul kriterleri
1. Araçlar:
   - `query_barcode`
   - `near_addresses(lat, lng, radius_m)`: kuryenin bugünkü durakları önce gelir.
   - `address_memory`
   - `write_memory(address_id, type, hint, window)`: `window` isteğe bağlı nullable dizi `[başlangıç, bitiş]` (dk; yalnız `lunch_break`)
   - `drop_record(record_id, rationale)`
   - `report_result(...)`: bitiş aracı.
2. `write_memory` şu durumlarda yazmayı reddetmeli ve modele yeniden yazmasını söylemelidir: kişisel veri (telefon, "hanım/bey" ile ad, yaş, sağlık, kişisel yargı), 140 karakteri aşan metin ya da bilinmeyen tür.
3. Gürültü notları kaydedilmemelidir (`status = noise`). Adres çözülemezse `status = uncertain` olmalı ve kuryeye tek bir soru dönmelidir.
4. Hafıza `MemoryBook`'tadır:
   - JSON dosyası (P0), bir günün D hafızasından tohumlanır.
   - Kayıt `pencere: [başlangıç, bitiş]` (öğle arası penceresi, dk) ve `source_list[]` (bağımsız kaynak kimlikleri) taşır. Rota bu alanları okur: `source_list` ≥ 2 ise kapanış planda ertelenir.
   - Geri bildirim: "geçerli" kaydı güçlendirir, "değişmiş" kaydı düşürür.
   - Süreli türlerin ömrü 10 gündür.
5. `MemoryAgent.process(..., address_id=None, source="agent")`: `address_id` verilirse (hasat cevabı) adres aranmaz, doğrudan o adrese bağlanır ve `source="harvest"` yazılır. Öğle arası cevabında "12 ile 1.5 arası" gibi metinden pencere çıkarılır (`parse_window`) ve yapılı alana yazılır. "Bildiğim sorun yok" → `noise` (kayıt yok).
6. `python -m agents.evaluate` notları `notes_truth.json` ile ölçmeli ve şunları raporlamalıdır: adres/tür doğruluğu, gürültü doğruluğu, kişisel veri sızıntısı, `parse_accuracy` önerisi.

### Gereksinim 4: Brifing Ajanı
**Kullanıcı hikayesi:** Yeni ya da ödünç bir kurye olarak, sabah ne beklediğimi duymak ve kapıda tek cümle ipucu almak istiyorum.

#### Kabul kriterleri
1. `route_risks` aracı şunları döndürmelidir:
   - durak ve gönderi sayısı, tahmini dönüş saati (`EtaModel`'den; planlanan süre değil, Faz 1'deki 15:36 ↔ 614 dk çelişkisi kapandı)
   - yabancı ve hafızalı durak sayıları
   - ipuçlu duraklar
   - öğle arası, cumartesi ve geçici kapanış uyarıları
2. Çıktı structured outputs ile alınmalıdır: `{morning_briefing, door_sentences[{address, sentence}], warnings[]}`. Sabah brifingi en fazla 70 kelime, kapı cümlesi en fazla 15 kelime olmalıdır.
3. Kapı cümleleri yalnızca hafızada kaydı olan durakları kapsamalı ve rota sırasıyla döndürülmelidir.
4. **Onaylı plan ve hafızalı rota (Faz 2):** `BriefingAgent(run, book, llm, plans=None)` rotayı müdürün onayladığı plandan (`SessionStore.plans`; yoksa simülasyon planı) alır ve `compute_route` ile hafızalı sırayı kurar. Sonuç `plan_source` (`approved_plan | simulation_plan`), `estimated_return`, `expected_min`, `route_changes[]` ve `route_comparison` taşır; rota değişiklikleri brifingde söylenir.
5. **İpucu süzme:** ipuçları güne ve saate göre süzülür (`hint_today_valid`): "Cumartesi kapalı" ipucu çarşamba söylenmez; öğle arası ipucu yalnız planlanan varış pencerenin içindeyse ya da pencereden kısa süre önceyse söylenir. Süzülen ipucu sayısı `filtered_hint` olarak döner. Tek kaynaklı kapanış rotada kaldığı için brifingde "kapıda teyit edin" olarak geçer.
6. **Sabah brifingi planlanan beklenen varışı kullanır**, simülasyonun gerçekleşen varışını değil (Faz 1'de gelecekten sızıntı vardı).

### Gereksinim 5: Hasat Ajanı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, kıdemli kuryenin kafasındaki bilginin tesadüfe kalmadan, hedefli sorularla toplanmasını istiyorum.

#### Kabul kriterleri
1. Araçlar (`HarvestTools`, deterministik):
   - `memory_gaps`: bugünkü planda bölgeye yabancı kuryenin gideceği, hafızası boş ve sık teslim alan adresler; adresi en son tanıdık olarak teslim eden kıdemliyi bulur.
   - `recurring_failure`: son günlerde aynı adreste tekrarlayan bilgiyle önlenebilir başarısızlıklar (hipotez kaynağı).
   - `save_questions`: bitiş öncesi toplu kayıt (iç içe strict şema). Tek tek kayıt canlıda geçmişi 30 kez yeniden gönderiyordu (~208 bin → ~26 bin girdi token/çağrı).
   - Bitiş aracı `harvest_plan`.
2. **Kurallar:** kurye başına günde ≤ 3 (`PER_COURIER`), şubede ≤ 30 soru (`DAILY_MAX`); boşluk sorusu yalnız yerel (ödünç olmayan) ve bugün çalışan kuryeye; **hipotez teyitsiz hafızaya yazılmaz** (Cumartesi → cumartesi kapalı, öğle penceresi → öğle arası, "giriş yapılamadı" → arka giriş …; teyit sorusu son deneyen kuryeye gider).
3. **Karar LLM'de, seçim ve sayılar araçta.** Mock'ta kurallı yedek aynı araçları aynı sırayla çağırır ve Orkestratör ile aynı iz biçimini (`agents/trace.py`) yazar; canlı yol aynı biçimi üretir (test).
4. `HarvestStore`: `plan(gün)`, `items(gün)`, `reply(question_id, text)` (bilinmeyen soru 404, cevaplanmış soru 409), `simulate_answer(question_id)`. Cevap Hafıza Ajanı'ndan `address_id` ile geçer. `HarvestTools` geçmişi `lru_cache` ile tutar (RunData nesnesi anahtar).
5. **`SeniorSimulator`** (yalnız demo): kıdemlinin cevabını simülasyonun gizli gerçeğinden üretir; sonuç açıkça `simulate: true` etiketlidir. Gerçekte cevap kuryenin uygulamasından sesle ya da yazıyla gelir. Gerçek cevap oranı ve doğruluğu bilinmiyor (`p_answer` VARSAYIM).
6. Cevaptan sonra `GET /api/route/...` rotanın değiştiğini göstermelidir (hafıza değişti → `same_as_sim: false`).

### Gereksinim 7: Teslim zamanı analizi ve saat teyidi (Faz 2b)
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanın bir adreste hep aynı saatte teslim edilemediğini kayıtlardan fark edip rotayı düzeltmesini, emin değilse kuryeye sormasını istiyorum.

#### Kabul kriterleri
1. `agents/delivery_time.py`: `TimeData(run)` (`delivery_log.json`'dan sayımlar, `findings(gün, adresler)`, `address_table`, `history`; yalnız hedef günden önceki satırlar: gelecekten sızıntı yok), `TimeSource` (`route`, `make_selection(gün, min_confidence, haric)`, `write_confirmation`, `reset`), `time_source(run)` (çalıştırma başına tek). Analiz `cm_sim.delivery_time` saf fonksiyonlarıyla yapılır (simülatörle aynı hesap).
2. `parse_confirmation(metin) -> (evet/hayır/None, dk/None)`: "evet" / "hayır" ve "3'ten sonra" gibi saat ifadesini çözer.
3. **Hasat:** yeni araç `time_confirmations {max_count}`; `save_questions` `reason` enum'unda `time` (`hypothesis_type: null`); soru "Bu adreste öğlen kimse yok gibi, doğru mu? Hangi saatte bulunuyorlar?". Kurallı yedek günde en çok 5 saat sorusu. Cevap Hafıza Ajanı'na gitmez, `TimeSource.write_confirmation`'a gider (metin `redact` ile ayıklanır). Teyitli bulgu güvenden bağımsız rotaya girer, reddedilen girmez. `SeniorSimulator` cevabı `truth.presence`'ten üretir (`simulate: true`). İstem `prompts/harvest.md` güncel.
4. `/api/memory/reset` zaman seçimini ve saat teyitlerini de sıfırlar.
5. Dürüstlük: gerçek veride başarısızlık saati boş; etki mekanizma olarak gösterilir.

### Gereksinim 8: Onarım rotayı uzatmaz ve kaydırılamayan bulgunun alternatifleri (Faz 2c)
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanın rotayı uzatmasını ya da kuryeyi fazla mesaiye sokmasını istemiyorum; bir durak bu kısıt yüzünden kaydırılamıyorsa bana alternatif (aktarma, ertesi gün, SMS) önerilmesini istiyorum.

#### Kabul kriterleri
1. `agents/route.py` `RoutePlanner` aynı `RepairLimits`'i config'ten kurar (`repair_limits(rc)`); ajan rotası simülatör rotasıyla 408/408 aynıdır. `plan()` çıktısı `time_unshiftable[]` (neden + metin), `comparison.route_constraint` (before_min, after_min, border_min, before_km, after_km, tolerans) ve `comparison.diff.time_unshiftable` taşır; değişiklik metinleri "rota süresi ±X dk" içerir.
2. `RoutePlanner.day_alternatives(day, mapping)` günün tüm rotaları için `cm_sim.routing_memory.time_alternatives`'ni çağırır; sonuç simülatörün kol D alternatifleriyle aynıdır (aynı fonksiyon). Karar müdürdedir; ajan alternatifleri uygulamaz, SMS metni yalnız öneridir (kişisel bilgi yok).
3. Mock kurallı yedek ve canlı yol aynı araçları aynı sırayla çağırır; kısıt kuralı iz'de bir "karar" cümlesiyle söylenir (bkz. `orchestrator` Gereksinim 1.11).
4. Dürüstlük: kısıt ve alternatifler mekanizmadır; gerçek veride saat boş, pilot ölçer.

### Gereksinim 6: Test
1. Sahte bir LLM (`_call` ezilerek) ile canlı döngü sınanmalıdır: araç çağrısı, bitiş aracı, `refusal`, araç hatası ve kişisel veri reddinden sonra yeniden yazma.
2. Mock yolları kritik gün ve kritik kurye için uçtan uca çalışmalıdır.
3. `agents/tests/test_phase2.py` (6 test): `compute_route` aracı simülatörle aynı sırayı üretir (408/408 rota), canlı hafıza rotayı oynatır, brifing onaylı planı + `EtaModel`'i okur ve ipucunu süzer, hasat akışı ve cevapları, hasat canlı yolu aynı iz biçimini üretir, `parse_window`.
4. `agents/tests/test_phase2_b.py` (7 hızlı + 1 yavaş): `agents.route` zaman onarımı simülatörle aynı sırayı üretir (408/408 rota), araç çıktıları ve seçim/hariç tutma, mock ve canlı yolun aynı araç sırası ve iz biçimi, `parse_confirmation`, hasat saat sorusu ve teyidin rotaya etkisi (teyitli girer, reddedilen girmez), gelecekten sızıntı yok.
5. `agents/tests/test_phase2_c.py` (7 hızlı): yayımlanan 408 rotada kısıt tutar; kaydırılan durak vardiya içinde; karşı-olguda planlanan süre ve fazla mesai artmaz; ajan alternatifleri = simülatör; mock izde `time_alternatives`; rota aracı kısıt ve kaydırılamayanları gösterir; demo örneği fazla mesaisiz.
