# Gereksinimler: API ve demo arayüzü

## Giriş

FastAPI, ajanları ve çalıştırma klasörünü tek sayfalık demo arayüzüne bağlar. Uç noktalar ve yanıt biçimleri `docs/sozlesmeler.md` §4'tedir. Arayüz dış bağımlılık kullanmaz; canlı demoda internet olmadan çalışmalıdır. **Referans ekran görüntüleri:** `docs/ekran_goruntuleri/` (1600×1000). Yeniden kurulumda görünüm ve içerik bunlara yakın olmalıdır.

## Gereksinim 1: API
1. §4'teki tüm uç noktalar uygulanmalıdır: `status, meta, summary, learning, economics, blocks, couriers, day, assignment/propose, assignment/ask, assignment/approve, briefing, note, memory, memory/summary, memory/geri-bildirim, memory/reset, speech`.
   - Değerlendirme dönemi dışındaki gün 404 dönmelidir; boş soru ya da not 400; sınır dışı ekonomi parametresi 422; bilinmeyen model ya da senaryo 400.
2. `Services` bir kez ve kilitle kurulmalıdır: eşzamanlı ilk istekler tek kurulumu bekler. Hafıza başlangıçta kritik günün D hafızasıyla tohumlanır.
3. Hafıza dosyası atomik yazılmalıdır (geçici dosya + `os.replace`). Bozuk dosya okunursa hafıza yeniden tohumlanır.
4. `/api/summary` → `calibration.rows` içinden `target` alanı çıkarılmalıdır; şirket içi toplu özet arayüze gönderilmez.
5. `/api/speech`: `CM_POLLY=1` ve mod `mock` değilse Polly `tr-TR` mp3 döner, aksi halde 501.
6. `/` adresi hikaye arayüzüne (`/story/`, Gereksinim 7) yönlenmeli; eski tek sayfa `/legacy` adresinde `ui/index.html` olarak kalmalı; `/ui/*` ve `/story/*` statik dosyaları servis etmelidir. (`ui-story/` yoksa `/` eski tek sayfayı verir.)
7. `api/tests/test_api.py` ve `api/tests/test_concurrency.py` yeşil olmalıdır.
8. Orkestratör uç noktaları (`/api/orchestrator/*`, `/api/plan/{day}`) `.kiro/specs/orkestrator/` Gereksinim 5'e göre uygulanmalı; `api/tests/test_orchestrator_api.py` yeşil olmalıdır.
9. **Faz 2 uç noktaları** (yanıt biçimleri `docs/sozlesmeler.md` §4 ve §6; **arayüz Faz 3'te yeniden yapılacak: burada yalnız veri ve uç nokta gereksinimi vardır**):
   - `GET /api/route/{day}/{courier}`: `compute_route` çıktısı (`comparison.{memoryless,memory}.order`, `changes[].text`, `diff`, `same_as_sim`) + `plan_source`. Canlı hafızayla; kurye planda yoksa 404.
   - `GET /api/orchestrator/candidates/{day}`: `{capacity, candidates}` ("kim gitsin"; LLM yok).
   - `POST /api/harvest/plan {day}`: hasat sonucu (iz + sorular); `GET /api/harvest/{day}` (yoksa 404); `POST /api/harvest/answer {question_id, text}` (bilinmeyen soru 404, cevaplanmış soru 409); `POST /api/harvest/simulate-answer {question_id}` (cevap gizli gerçekten, `simulate: true`).
   - `GET /api/learning`: `learning.json` (Hedef 1) ya da 404.
   - `GET /api/summary` yeni alanlar: `learning_same_route`, `learning`, `ablation`; `summary.memory_routing`; `sweep.headline`; `meta.critical.memory_gain`.
   - `GET /api/status` → `models` içinde `orchestrator` ve `harvest`; `GET /api/briefing/{gün}/{kurye}` yeni alanlar (`plan_source`, `estimated_return`, `route_changes`).
   - `api/tests/test_phase2_api.py` (3 test) yeşil olmalıdır.
10. **Faz 2b uç noktaları** (geriye uyumlu; biçimler `docs/sozlesmeler.md` §4 ve §7; Faz 2c için §8; yeni ekran zorunlu değil):
    - `GET /api/time/example`: demo örneği (`example`, `agent{finding, table, history}`, `route{change, same_as_sim, diff}`, `hidden_truth`, `summary`); örnek yoksa 404.
    - `GET /api/time/{day}?min_confidence=`: `delivery_time_analysis` çıktısı + `selection{min_confidence, excluded, applied}`.
    - `GET /api/time/{day}/address/{address}`: `history[{day, weekday, hour, slot, result}]`, `table`, `finding`, `confirmation`.
    - `GET /api/route/...` yeni alanlar (`comparison.no_time`, `time_findings[]`, `diff.time_carried`, `expected_absence`); `POST /api/harvest/answer` zaman dalı (saat teyidi `TimeSource`'na gider, Hafıza Ajanı'na değil); `POST /api/memory/reset` zaman seçimlerini ve teyitleri de sıfırlar; `GET /api/summary` → `time` (`summary.time_analysis`).
    - Arayüz gösterebilir (dış bağımlılık yok): adres geçmişi (saat → sonuç), bulgu ve güven, rota değişikliği (1 tabanlı sıra), sonuç (zamansız ↔ hafızalı). Dürüstlük notu: "seçilmiş örnek; büyüklük `summary.time_analysis`; gerçek veride saat boş, pilot ölçer".
    - `api/tests/test_phase2_b_api.py` (3 hızlı test) yeşil olmalıdır.
11. **Faz 2c uç noktaları ve alanları** (geriye uyumlu, yeni alanlar):
    - `GET /api/time/example` → yeni `example.route` (limits, planlanan/gerçekleşen dk, km, overtime_min zamansız/hafızalı, shift_end), `constraint` (= `summary.time_analysis.constraint`), `example_constraint` (= `meta.time_example_constraint`: kısıt yüzünden kaydırılamayan bulgu + alternatifi).
    - `GET /api/time/{gün}/alternatives` → `{unshiftable, transfer, next_day, evening_delivery_point, proposals[], constraint{tolerance_min, tolerance_km, band_min, shift_end}, rule}`.
    - `GET /api/route/{gün}/{kurye}` → `time_unshiftable[]`, `comparison.route_constraint`, `diff.time_unshiftable`.
    - Dürüstlük notu: alternatifler öneridir, karar müdürdedir; simülasyon uygulamaz.
    - `api/tests/test_phase2_c_api.py` (3 hızlı test) yeşil olmalıdır.

## Gereksinim 2: Genel arayüz
1. Dosyalar:
   - `ui/index.html`
   - `ui/style.css`
   - `ui/common.js`: biçim (`%95,8`, `1.234`), API istemcisi, ipucu, bildirim, ses
   - `ui/map.js`: SVG harita
   - `ui/chart.js`: SVG çizgi, çubuk ve nokta grafikleri; ipucu ve "Tablo" görünümü
   - `ui/app.js`: ekranlar
   Vanilla JS, derleme yok, CDN ya da harita karosu ya da web fontu yok.
2. Üst bar:
   - dört sekme (kısayol 1–4)
   - gün seçici (değerlendirme günleri; varsayılan `meta.critical.day`, "demo günü" etiketli)
   - her zaman görünen "Uygulama verisi · 1 aylık geçmiş" etiketi
   - mod rozeti (`/api/status`; ipucunda ajan başına modeller). Bir ajan yanıtı `degraded` dönerse "Çevrimdışı yedek" uyarısı.
3. 1600×1000'de her sekme kaydırmasız açılmalıdır. Dil `sunum-dili.md`'ye uymalıdır: "kâr" ve "performans puanı" yok; "operasyon maliyeti tasarrufu", "kendi bölgesinde", "çekirdek bölge" var. Kol adları `meta.arms`'tan gelir.
4. Grafikler `dataviz` yöntemine uymalıdır. Kol renkleri: D mavi, C turuncu, B yeşil-mavi, A sarı. Rotalar kurye türüne göre renklenir: kıdemli gri, yedek pembe, yeni yeşil, ödünç mor.

## Gereksinim 3: Şube ekranı (`docs/ekran_goruntuleri/1_sube.png`)
1. **Sol:** D kolunun günlük haritası.
   - SVG blok altlığı (türüne göre soluk ton), rotalar, duraklar (başarılı / başarısız / ertelendi / ipuçlu).
   - Seçili küme vurgulanır; yakınlaştırma ve kaydırma `viewBox` ile.
   - Üst satır: küme, durak, ipuçlu ve başarısız sayıları ile "kendi bölgesinde" payı.
2. **Orta:** "Atama önerisi".
   - `POST /api/assignment/propose` çağrılır.
   - Beklenen başarısız teslim (geçmişe bakmadan → önerilen çubukları), yabancı/hafızalı durak sayısı, çalışmayan ve boştaki kuryeler.
   - "Kuryeler durakların %X'inde kendi bölgesinde; dinamik plan yalnız sınırları esnetir" cümlesi.
   - Tablo sütunları: küme, kurye adı + tür rozeti, durak, beklenen başarısız, hafızalı/yabancı.
3. **Sağ üst:** Gerekçe ve öne çıkanlar; katlanır "Ajan ne yaptı?" (`steps`).
4. **Sağ alt:** "Ya şöyle olursa?" sohbeti.
   - Hazır soru çipleri kritik kuryeye göre kurulur ("X yerine yedek kurye gönderirsem?", "X bugün gelmezse?", "X yerine Y gönderirsem?").
   - `POST /api/assignment/ask` (`current` = ekrandaki atama) çağrılır. Yanıttaki `assignment` tabloya işlenir, değişen satır vurgulanır ("önceki: X"), `diff` etiketleri gösterilir.
   - "Öneriye dön" ve "Onayla" düğmeleri; onay `POST /api/assignment/approve` ile.

## Gereksinim 4: Kurye ekranı (`2_kurye.png`)
1. **Telefon çerçevesi.**
   - Kurye adı ve tür rozeti; sabah brifingi (`GET /api/briefing/{gün}/{kurye}`) ve "Dinle" düğmesi. Ses önce `/api/speech`, 501 gelirse `speechSynthesis` tr-TR.
   - Uyarılar.
   - Kapı kartı: büyük tek cümle ve kayıt türü, "✓ Hâlâ geçerli / ✗ Değişmiş" düğmeleri. Geri bildirim `door_sentences[].records[].id` ile `POST /api/memory/feedback`'e gider; bu alan yoksa adres sorgusuna düşer.
2. **Harita.**
   - Kuryenin rotası; "Rotayı oynat" (1× hızda ~40 sn, 0,5×–4×).
   - İpuçlu durakta işaretçi cümle okunana kadar bekler; durak sonuçları işaretçi geçtikçe ortaya çıkar.
   - Durak şeridi; tıklanan durağa atlanır.
3. **Not bırak.**
   - Metin kutusu; `webkitSpeechRecognition` varsa "Bas-konuş".
   - Örnek çipler: biri kişisel veri içerir, biri gürültüdür.
   - `POST /api/note` çağrılır; konum işaretçinin bulunduğu duraktır.
   - Sonuç kartı: durum, adres, tür, kaydedilen ipucu, "Kişisel veri ayıklandı" rozeti, ajan adımları. Sonraki günlerde aynı adrese giden kurye için "brifingini aç" bağlantısı.

## Gereksinim 5: Simülasyon ekranı (`3_simulasyon.png`)
1. "Demo senaryosu · 20 gün / Uzun dönem · 60 iş günü" geçişi (`/api/summary` → kök alanlar ve `long_term`).
2. Dört kol KPI kartı: ilk denemede teslim, önlenebilir başarısızlık, kurye/gün, vardiya bandında, **kendi bölgesinde** (= 1 − `unfamiliar_share`), hafıza kapsamı; altında `deltas` satırı.
3. **Demo görünümü:**
   - günlük ilk denemede teslim çizgisi (tıklanan gün seçiciyi değiştirir)
   - başarısızlık nedenleri (önlenebilir olanlar vurgulu)
   - yeni/ödünç kurye öğrenme eğrisi (C ve D)
   - "Haritada karşılaştır" (A ile D ya da B ile D, eşzamanlı yakınlaşma)
4. **Uzun dönem görünümü:**
   - "Hafıza birikiyor": D − C farkı ve D hafıza kapsamı, 5 günlük hareketli ortalama.
   - **Net mesaj kartı:**
     - Başlık: "Kaydırmıyoruz: kuryeler durakların %X'inde kendi bölgesinde; değişen yalnız sınırlar. Aynı iş günde N kurye daha az, kalite bugünkü düzeyde."
     - Tablo (Bugün / Ajansız geçiş [RİSK] / Courier Memory): kendi bölgesinde durak payı, kurye/gün, başarısız teslim/gün, fazla mesai saat/gün, iş yükü sapması.
     - İlk denemede teslim yüzdesi yalnız küçük ayrıntı satırında.
5. **Sağlamlık:** `sweep.json` varsa dört kaydırıcı (`keys/values`) ile eşleşen satırın kolları ve `sweep.headline` aralıkları: "D − A ilk denemede −0,13 … +0,12 puan (kombinasyonların %100'ü ±0,15 içinde), kurye-gün −%7,9 … −%6,5; D − C +0,12 … +0,42 puan (hepsi pozitif)" (`D_vs_A_pp`, `courier_day_D_vs_A_pct`, `D_vs_C_pp`). "D ≥ C ≥ B %X" (`order_share`) manşet olarak gösterilmez (B rastgele atama; önemsiz sıralama).
6. **Kalibrasyon:** Katlanır "14/14 ✓ Uygulama verisi, saha verisinden türetilmiş toplu hedeflere kalibre". Satırlarda yalnız ölçü, uygulama değeri ve uyum; hedef değerler gösterilmez.
7. Uyum tahmincisi notu (`recovery`) ve "Bu rakamlar ne anlatır?" açıklaması.

## Gereksinim 6: Değer ekranı (`4_deger_temkinli.png`, `5_deger_optimize.png`)
1. **Manşet** (`/api/economics` → `headline`):
   - Cümle: "Şube başına yılda **X milyon TL** daha düşük operasyon maliyeti · gönderi başına **A → B TL** · başarısız teslim bugünkü düzeyde".
   - Altı kutu: günlük tasarruf (vurgulu, yüzde), yıllık tasarruf, gönderi başı önce→sonra, başarısız teslim/gün (bugün · ajansız · hafızalı), "Ajansız geçişin ek maliyeti" (uyarı tonu), "LLM maliyetinin tasarrufa oranı".
2. **Operasyon maliyeti şelalesi** (`operation.waterfall`): sekmenin en büyük görseli.
   - Başlangıç ve sonuç tam sütun; azalışlar yeşil, artış uyarı rengi.
   - Açıklamalar `code` alanına bağlıdır (`bugun, dinamik, ajansiz, atama, hafiza, sonuc`) ve `operation.arms` farklarından üretilir.
   - TL/gün ↔ TL/yıl geçişi; tablo görünümü; "tasarrufun çoğu kurye-gününden; kurye günlük maliyeti VARSAYIM" satırı.
3. **Üç durum yan yana** (A, B [RİSK], D vurgulu; isteğe bağlı C): kendi bölgesinde, kurye, başarısız teslim, fazla mesai, operasyon maliyeti, gönderi başına, yıllık fark. Her hücrede bugüne göre fark.
4. **Ajanların maliyeti ve getirisi:**
   - İki tıklanabilir senaryo kartı: Temkinli / Optimize (`llm_scenarios`; seçince `?scenario=` ile tüm sekme yeniden hesaplanır). Not: "Optimize: kalite canlı ölçümle doğrulanır".
   - "Maliyet kırılımı / Getiri hesabı" geçişi:
     - Maliyet kırılımı: ajan bazında çağrı/gün, token/çağrı, TL/çağrı, TL/gün, `source` rozeti; ajan başına model seçicileri ve önbellek kutusu.
     - Getiri hesabı: Hafıza + Brifing kazanç şelalesi ile `vs_C` ve `vs_B` (üst sınır).
5. **Varsayımlar:** kaydırıcılar (kurye günlük maliyeti 2.000–6.000, kur 30–60, başarısız deneme diğer 0–100, km 2–12, senaryo sorusu 0–10). VARSAYIM etiketi, "Sıfırla" düğmesi, 250 ms gecikme (eski istek yenisinin üstüne yazamaz).
6. **Ölçek:** 1/10/100 şube için operasyon tasarrufu, ajansız ek maliyet, LLM, Hafıza + Brifing net; altında model karşılaştırma çubukları.

## Gereksinim 7: Hikaye arayüzü (Faz 3; `ui-story/`, `/story/`)

Demo ve sunum aynı ekrandır: sunucu → ile adım adım ilerler, her adım canlı API'ye bağlıdır. Eski tek sayfanın (Gereksinim 2–6) içerikleri sahnelere taşınmıştır. Eski sayfa `/legacy`'de yalnız **serbest keşif** için kalır: herhangi bir gün/kurye seçimi, A ↔ D harita karşılaştırması, durak şeridi ve oynatma hızı, demo ↔ uzun dönem KPI geçişi, "hafıza birikiyor" eğrisi, Atama Ajanı'nın tek başına öneri/soru ekranı (hikayede Orkestratör üstlenir), TL/gün ↔ TL/yıl geçişi ve getiri şelalesi.

1. **Denetim:** → / boşluk / Enter / PageDown sonraki adım, ← geri, R sahneyi baştan, A açıklama satırı, 1–8 sahne; adres `#sahne/adım`. **Açıklama satırı (Faz 5):** her adımda alt çubuğun üstünde "Ne oluyor · Ekranda · Veri" (`js/narration.js`); rakam içermez, neyin nasıl gösterildiğini ve verinin kaynağını (gerçek veri / simülasyon / ajan aracı / VARSAYIM) söyler; varsayılan açık, A ile kapanır, tercih tarayıcıda saklanır. Sahne 2 vuruş grubuna göre anlatır. Yazı alanındayken kısayollar çalışmaz. Sahnenin bekleyen eylemi varsa (ör. "Bugünün soruları", "Simüle kıdemli cevaplasın") → önce onu çalıştırır.
2. **İnternetsiz:** MapLibre yerel kopyası (`vendor/`), yerel vektör karolar (`tiles/`, Beykoz z8–14 + bağlam z7–10), yerel yazı tipleri; karo yoksa çevrimiçi OpenFreeMap. WebGL yoksa 2D tuval yedeği (`?2d`).
3. **API yoksa:** Sahne 2 `data/trace_fallback.json`'u, Sahne 3–7 `data/fallback.json`'u oynatır; rozet "API yok · kayıtlı yanıt". Kayıtlar `tools/record_trace.py` ve `tools/record_fallback.py` ile mock modda üretilir. Serbest soru/not ve ekonomi kaydırıcıları canlı API ister (kayıtta yoksa açık uyarı).
4. **Sahneler:**
   1. *Sorun ve ilke*: açılış (sokak düzeyinde Beykoz, "Sitenin girişi arka sokaktan"); gerçek veriyle (Gereksinim 7.6) 18 sabit bölge → yeni yapının dinamik bölgeleri → ertesi gün → geçmişe bakmadan atamada yabancı sokak payı; ilke (uygulama verisi, atıf değişir): kendi bölgesinde durak payı A/B/D (`long_term.summary.arms.*.unfamiliar_share`); ajanlar şeması (Orkestratör + dört ajan, araç adları kodla aynı) ve tek maliyet fonksiyonu.
   2. *Sabah*: `POST /api/memory/reset` + `/api/orchestrator/start` + SSE iz (poll ve kayıtlı iz yedeği); her araç adımı haritada; öneride durur, "Müdür ekranı" Sahne 3'e geçer.
   3. *Onay*: aynı koşunun önerisi (yoksa `/api/orchestrator/plan`): gerekçe, ödünç kuryelerin kümeleri; riskler (bant üstü ilk 3 küme, kaydırılamayan teslim saati → alternatif + SMS, müdür kararı); "X gelmezse ne olur?" çipleri ve serbest soru (`/session/{id}/ask`; iki yol kartı, değişen kümeler haritada); ONAYLA (`/session/{id}/decision`, iz'de İNSAN satırı).
   4. *Kapıda* (Gökhan, O02): telefon çerçevesi; sabah brifingi + Dinle (`/api/speech`, 501 → tarayıcı sesi); rota oynatma, notlu durakta tek cümle + "✓ Hâlâ geçerli / ✗ Değişmiş" (`/api/memory/feedback`); not bırak (çipler: kişisel veri, gürültü, püf noktası; serbest metin + bas-konuş; `/api/note`; "Kişisel veri ayıklandı" rozeti); aynı adrese günler sonra giden başka kuryenin brifinginde bu not (`demo.next`); aynı rota hafızasız ↔ hafızalı (`meta.critical.memory_gain` + `summary.memory_routing.type` dağılımı).
   5. *Hasat*: `/api/harvest/plan` izi ve soru adresleri (boşluk / hipotez / saat); Gökhan'ın rotasındaki boşluk sorusu → simüle kıdemli (açıkça etiketli) → Hafıza Ajanı → rota farkı (`/api/route` önce/sonra); saat teyidi → teslim saati kaydırılır; kayıtlardan kalıp (`/api/time/example`: saat × gün grafiği, rota süresi farkı).
   6. *Öğrenme*: Hedef 1 eğrisi (`/api/learning`; C, D, D hafızasız; %95 bant; kıdemli düzeyi); dört yapı gün gün (`daily.*.first_attempt_rate`) + başarısızlık nedenleri (`summary.arms.*.fail_by_reason`, önlenebilirler kalın); sağlamlık (`sweep.rows` → D − A ve D − C noktaları, `sweep.headline`); kalibrasyon tablosu (ölçü, uygulama değeri, uyum; hedef yok); ablasyon tablosu (her satır ayrı simülasyon).
   7. *Değer*: manşet (`headline`), şelale (`operation.waterfall`), dört durum tablosu (`operation.arms` + uzun dönem kendi bölgesinde payı), ölçek 1/10/100 şube (`operation.scale`, `scale`) + tek model karşılaştırması (`model_comparison`), LLM temkinli ↔ optimize (`llm_scenarios`, ajan kırılımı) + ajan başına model ve önbellek seçici (`/api/economics?model_assignment&model_memory&model_briefing&cache`), varsayım kaydırıcıları (`/api/economics?...`, 160 ms gecikme, sınır dışı yanıt eski çizimi korur).
   8. *Kapanış*: AWS + Kiro (ajan başına model ve mod `/api/status`'dan canlı; spec, görev ve test sayıları), sorumlu yapay zekâ (dört ilke), pilot (4 hafta, tek şube, A/B; ölçülecekler), tek cümle + manşet (`/api/economics`).
5. **Görsel ve dil:** referans görüntüler `docs/ekran_goruntuleri/hikaye/1_sorun.jpg` … `8_kapanis.jpg`; 1600×1000 kaydırmasız; her sahnede "Uygulama verisi · 1 aylık geçmiş" atfı; grafikler dataviz yöntemine uyar (2px çizgi, %10 bant, lejant + seçici doğrudan etiket, ipucu, "Tablo" görünümü; kol renkleri `ui/` ile aynı doğrulanmış yuvalar). Dil `sunum-dili.md`: performans puanı ve kurye sıralaması yok; simüle cevap ve seçilmiş örnekler etiketli; "bu varsayımlar altında".
6. **Gerçek harita** (`veri-kurallari.md` → Gerçek harita): Sahne 1 gerçek Beykoz teslim noktaları ve sabit bölge poligonlarını gösterir; sim adresleri Beykoz teslim noktalarına deterministik eşlenir (`data/sim_mapping.json`). Barkod, kurye kimliği, bölge kodu, şube kimliği ve şirket içi sistem adları çıktıya girmez (`sim/tests/test_forbidden_content.py`).
7. Doğrulama: başsız tarayıcıda 1–8 sahneleri API açıkken ve kapalıyken (`?api=http://127.0.0.1:9`) konsol hatasız gezilir; `pytest` yeşil.

