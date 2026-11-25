# Tasarım: Ekonomi

- `agents/llm.py`: Her isteğin `usage` değeri `_log_usage` ile JSONL dosyasına yazılır (yalnız `live` ve `record` modlarında). `CM_AUTO_CACHE=1` (varsayılan) üst düzey `cache_control` ekler, böylece önceki turlar önbellekten okunur.
- `agents/cost.py`:
  - `MeasurementLLM`, `_call` metodunu ezer, senaryodaki yanıtları döndürür ve istekleri kaydeder.
  - Temsili diziler:
    - Atama önerisi: özet → çöz → küme → kaydet
    - Soru: çöz → yanıtla
    - Hafıza: yakın adresler → hafıza → yaz → sonuç
    - Brifing: riskler → JSON
    - Orkestratör ve Orkestratör sorusu: kurallı yedeğin izinden kurulan çağrı dizisi
    - Hasat: boşluklar → tekrarlayan başarısızlık → toplu kayıt → plan (toplu `save_questions` ~208 bin → ~26 bin girdi token/çağrı)
    - Hasat cevabı: Hafıza Ajanı profili, günde ~26 çağrı
  - `_measure`: Ön ek (araçlar + sistem) ve mesaj karakterleri ölçülür. Önbellekli modelde ilk istek tamamını yazar; sonraki istekler bir öncekinin tamamını okur ve yalnız yeni kısmı yazar.
- `agents/economics.py`:
  - `load_assumptions(overrides)` ve `compute(run, tokens, assumptions)`.
  - Kurye dakikası = gün maliyeti / vardiya dakikası.
  - Başarısız deneme maliyeti = ikinci deneme dakikası × kurye dakikası + km × km maliyeti + diğer.
- Manşet hesap önbelleksizdir (temkinli). Önbellekli tahmin, anahtar açılınca gösterilir.
