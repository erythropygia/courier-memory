# Tasarım: API ve arayüz

**API (`api/main.py`):**
- Pydantic istek modelleri: `DayRequest`, `QuestionRequest(day, question, history, current)`, `ApprovalRequest`, `NoteRequest`, `Feedback`.
- Onaylanan atama bellekte tutulur ve sonraki soruların temeli olur.
- `sv()` `threading.Lock` ile `lru_cache`'li kurucuyu sarar; testler için `sv.cache_clear` sunar.
- `/api/economics`, `agents.economics.compute`'u istek başına çağırır (hesap ucuzdur).
- `/api/route/{day}/{courier}` canlı hafıza + onaylı plan/simülasyon planıyla `compute_route`'yı çağırır; `/api/harvest/*` `Services.harvest` (`HarvestStore`) üzerinden; `/api/orchestrator/candidates/{day}` `DayTools` araçlarını LLM'siz çağırır; `/api/learning` ve `/api/summary` yeni alanları `data/demo_run/` dosyalarından okur.
- `/api/time/example`, `/api/time/{day}`, `/api/time/{day}/address/{address}` `Services` üzerindeki `TimeSource`'nı ve `meta.time_example` / `summary.time_analysis`'ni okur; `/api/harvest/answer` zaman sorusunu `TimeSource`'na yönlendirir; `/api/memory/reset` zaman durumunu da sıfırlar.
- `/api/time/{day}/alternatives` `RoutePlanner.day_alternatives`'ni çağırır; `/api/time/example` `example.route`, `constraint`, `example_constraint` (`meta.time_example_constraint`) alanlarını ekler; `/api/route` `time_unshiftable[]` ve `comparison.route_constraint` taşır.
- `/` → `/story/` yönlendirmesi; eski tek sayfa `/legacy`. Hikaye arayüzünün tasarımı aşağıda.

**Eski tek sayfa (`ui/`, `/legacy`):**
- Ortak durum: `meta`, `day`, `blocks`, `summary`.
- Sekmeler tembel çizilir; gün değişince açık sekme yeniden çizilir.
- Harita bileşeni bir sınıftır: altlık ızgara bir kez çizilir; katmanlar rota, durak ve vurgu. Yakınlaştırma `viewBox` ile. Karşılaştırma görünümünde iki harita eşzamanlı yakınlaşır.
- Grafik fonksiyonları kap genişliğine göre çizilir, gizli kapta çizim atlanır. Her grafikte "Tablo" düğmesi erişilebilir alternatif sunar.
- Oynatma `requestAnimationFrame` ile ilerler: işaretçi duraklar arasında hareket eder, kapı cümlesi olan durakta ses bitene kadar bekler.
- Değer sekmesi:
  - `scenario` ve parametre kaydırıcılarından sorgu dizesi kurulur.
  - Yanıtlar istek sayacıyla sıralanır; eski yanıt atılır.
  - Yükleme sırasında önceki görüntü soluk kalır.
- Görsel hedef: `docs/ekran_goruntuleri/*.png`.

**Hikaye arayüzü (`ui-story/`, `/story/`; Gereksinim 7):**
- Dosyalar: `index.html`, `story.css`; `js/expression.js` (MapLibre ifadeleri + 2D yorumlayıcı), `js/style.js` (harita stili), `js/stage.js` (ara değerli durum `CM.S`, harita sarmalayıcı `CM.H`, işaretler, rakam/mesaj/eylem/kart), `js/common.js` (`CM.api` kayıt yedekli istemci, `CM.traceRow/writeTrace` ajan izi, `CM.speech`, `CM.board`/`CM.side`, sim adresi → konum), `js/chart.js` (çizgi + bant, şelale, aralık şeridi, teslim zamanı grafiği; ipucu ve "Tablo"), `js/scene1.js` … `js/scene7.js`, `js/main.js` (sunucu denetimi).
- Sahne nesnesi: `{no, name, title, attribution, stepCount, enter(), step(i, previous), leaving(), pending?}`; Sahne 2 kendi `next/back`'sini kullanır (iz geldikçe vuruş vuruş). Her `step` çağrısı sahne sayacını artırır; geç gelen API yanıtı sayaç değiştiyse çizilmez.
- Harita: animasyon sırasında veriye bağlı boya ifadesi değiştirilmez; dalga etkisi için özellikler gecikmeye göre "kutu" katmanlarına ayrılır (`stage.js` notu). Gizlenen HTML işaretleri görünürlükle de gizlenir (MapLibre opaklığı kendisi yazar).
- `CM.api(path, body?, {name})`: anahtar `"GET /api/..."` ya da `"POST /api/...#name"`; ağ hatası/zaman aşımında `data/fallback.json`'a düşer ve oturum boyunca öyle kalır; HTTP hataları hata olarak döner. `fallback.json → demo`: Sahne 4–5'in kurallı demo seçimleri (`tools/record_fallback.py` hesaplar; `docs/sozlesmeler.md` §9).
- Canlı hafıza: Sahne 2 koşudan önce `/api/memory/reset {day: 32}` çağırır; böylece prova tekrarları aynı başlar. Sahne 4 notu ve Sahne 5 cevapları hafızayı değiştirir (hikayenin parçası).

