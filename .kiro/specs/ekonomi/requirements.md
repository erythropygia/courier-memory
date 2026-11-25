# Gereksinimler: Ekonomi (token maliyeti ↔ kazanç)

## Giriş
Jüri ve şirket iki soruyu soracak: "Bu kaça mal oluyor?" ve "Ne kazandırıyor?". Bu spec, ajanların token maliyetini işlem hacmiyle birlikte hesaplar ve simülasyondaki operasyonel kazançla karşılaştırır. Sonuçlar şube-gün, işlem başı, yıllık ve ölçek (1/10/100 şube) düzeyindedir. Sözleşme: `docs/sozlesmeler.md` §1 (`token_usage.json`, `economics.json`) ve §4 (`GET /api/economics`).

### Gereksinim 1: Token kullanımı
1. Canlı ya da kayıt modunda her LLM isteğinin kullanımı `data/usage.jsonl` dosyasına yazılmalıdır: `agent`, `model`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `seconds`.
2. `python -m agents.cost` ajan çağrısı başına token değerini üretmelidir:
   - Ölçüm varsa ölçüm kullanılır.
   - Yoksa her ajan için gerçek araç çıktılarıyla kurulan temsili çağrı dizisinden istek boyutu ölçülür; token ≈ karakter/3. Önbelleksiz ve önbellekli değerler ayrı verilir.
   - Her değer `source` alanıyla (`estimate` ya da `measurement`) etiketlenir.

### Gereksinim 2: Ekonomi hesabı
1. Varsayımlar `agents/economics.yaml` içinde olmalıdır: kur, kurye-gün maliyeti, km maliyeti, başarısız deneme bileşenleri, fazla mesai çarpanı, model fiyatları, ajan başına model, günlük soru sayısı. Yer tutucular `ASSUMPTION` etiketi taşımalıdır.
2. Hacim simülasyondan alınmalıdır; uzun dönem çalıştırması varsa o kullanılır:
   - not/gün → Hafıza Ajanı çağrısı
   - kurye/gün → Brifing Ajanı çağrısı
   - 1 öneri + N soru → Atama Ajanı çağrısı
   - Faz 2: günlük çağrılara `orchestrator` (1), `ask_orchestrator` (3), `harvest` (1) ve `harvest_answer` (günde sorulan hasat sorusu kadar Hafıza Ajanı çağrısı, ~26/gün; `memory` profili) eklenir. Atama Ajanı da sayılmaya devam eder (temkinli). Orkestratör ve hasat token tahmini kurallı yedeğin izinden kurulan çağrı dizisiyle ölçülür.
3. Kazanç iki karşılaştırmayla hesaplanmalıdır: D'nin C'ye göre katkısı (manşet, temkinli) ve D'nin B'ye göre katkısı (üst sınır). Bileşenler:
   - önlenen başarısız ilk deneme × deneme maliyeti
   - önlenen fazla mesai × kurye dakikası × çarpan
   - kapasite (kapıda kazanılan dakika): ayrı gösterilir, getiriye katılmaz
4. Çıktılar:
   - LLM maliyeti (gün, gönderi başı kuruş, not başı, brifing başı)
   - doğrudan kazanç, net kazanç, getiri katı
   - yıllık şube ve ölçek tablosu
   - model karşılaştırması (bilgi amaçlı; varsayılan model değişmez)
   - dinamik planlamanın bağlam kazancı (bu çalışmanın değil)
5. `GET /api/economics` sorgu parametreleriyle varsayımları ezip anında yeniden hesaplamalıdır. Bilinmeyen model için 400 dönmelidir.

### Gereksinim 3: Arayüz ("Değer" sekmesi)
1. Manşet: gönderi başına kuruş, LLM TL/gün, doğrudan ve net kazanç/gün, getiri katı. B'ye göre değerler "üst sınır" etiketiyle gösterilir.
2. Maliyet kırılımı ajan bazında olmalıdır. Model seçici ve önbellek anahtarı bulunmalı, yanında "kalite canlı ölçümle doğrulanmalı" notu olmalıdır.
3. Kazanç bileşenleri, varsayım kaydırıcıları, ölçek tablosu ve model karşılaştırması gösterilmelidir.

### Gereksinim 4: Test
`agents/tests/test_economics.py` ve `api/tests/test_api.py::test_economics_endpoint` yeşil olmalıdır. Testler şunları sınar: yapı, başarısız deneme maliyetine göre monotonluk, daha ucuz modelin daha düşük maliyet vermesi, önbelleğin maliyeti artırmaması.

### Gereksinim 5: Operasyon maliyeti manşeti ve LLM senaryoları
1. Kol başına operasyon maliyeti hesaplanmalıdır: kurye-gün × maliyet + fazla mesai + başarısız teslim × deneme maliyeti + km × km maliyeti + LLM.
2. Manşet A ile D arasındaki tasarruftur (gün, yıl, gönderi başı önce/sonra, kalite: başarısız teslim/gün). Ajansız geçişin ek maliyeti (B − A) ayrıca gösterilir.
3. Şelale şu adımlardan oluşmalıdır: `bugun → dinamik → ajansiz → atama → hafiza → sonuc`. Her adım `code`, `step`, `type` ve `tl_day` alanlarını taşır; ara adımların toplamı başlangıçtan sonuca götürür.
4. LLM senaryoları `agents/economics.yaml → senaryolar` içinde tanımlanır:
   - temkinli: Opus 5.5, önbelleksiz
   - optimize: önbellek açık, Hafıza/Brifing Haiku 5.5, Atama Sonnet 5.5
   `?scenario=` ile seçilir; yanıt her senaryonun LLM maliyetini ve tasarrufa oranını döndürür.
5. Ajan başına model çalışma zamanında da seçilebilmelidir (`CM_MODEL_ASSIGNMENT/MEMORY/BRIEFING/ORCHESTRATOR/HARVEST`). Kalite `agents.evaluate` ile her model için ölçülür. `agents/economics.yaml → agent_model` ve senaryolar `orchestrator` ve `harvest` anahtarlarını içerir (temkinli: ikisi de Opus 5.5; optimize: Orkestratör Sonnet 5.5, Hasat Haiku 5.5).
6. Faz 2 rakamları (uygulama verisi, temkinli): LLM maliyeti 139 → 206 TL/gün (orkestratör + hasat dahil); hafızanın getirisi 10,7× → 7,6×; optimize senaryo ~16 TL/gün. Operasyon tasarrufu (A → D) 8.854 → 8.539 TL/gün. Yeniden üretim: `python -m agents.cost && python -m agents.economics`.
