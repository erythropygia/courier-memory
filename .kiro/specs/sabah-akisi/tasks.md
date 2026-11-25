# Uygulama planı: Sabah akışı

- [x] 1. Simülatör: `config.Morning`, `S_MORNING`, çıkış saati, vardiya bitişinden fazla mesai, `RepairLimits.shift_end_at`, `current_morning` karşı-olgusu, `summary.morning`; `sim/tests/test_morning.py`
  - _Gereksinimler: 1.1–1.6, 1.8_
- [x] 2. Deneyler: tarama ve öğrenme sabahı eşitler; ablasyon `full_morning` ve `morning` çifti
  - _Gereksinimler: 1.7_
- [x] 3. Ajan: `morning_info`, `plan_departure`, rota ve brifing çıkış saati; Orkestratör `sorting_plan`, öneride `morning`; istem; `agents/tests/test_morning_agent.py`
  - _Gereksinimler: 2.1–2.4_
- [x] 4. API `/api/morning/{gün}`, `/api/morning/scan`; `api/tests/test_morning_api.py`
  - _Gereksinimler: 3.1, 3.2, 3.4_
- [x] 5. Ekonomi: şelalede "Sabah" kalemi, hafızanın getirisi yalnız hafıza; sunum rakamlarında sabah bölümü
  - _Gereksinimler: 4.1, 4.2_
- [x] 6. Hikaye: Sahne 3 indirme adımı, Sahne 2 vuruşu, Sahne 7 şelale; kayıtlı yanıtlar
  - _Gereksinimler: 3.3_
- [x] 7. Yeniden üretim zinciri ve ölçüm raporu (`docs/olcum-sabah.md`); belgeler
  - _Gereksinimler: 4.3_
