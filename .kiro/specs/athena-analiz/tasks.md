# Uygulama planı: Athena analizi ve Analiz Ajanı

1–7 repoda yapıldı ve AWS'ye gitmeden sınandı. 8–10 dağıtım hesabında yapılır.

- [x] 1. `deploy/athena/athena_setup.py`: `TABLES`, `build_rows` (saf, yalnız çalıştırma klasörü), `create_table_sql`, JSON Lines + gzip
  - _Gereksinimler: 1.3, 1.6, 2.1–2.5_
- [x] 2. AWS kurulumu: bucket (herkese açık erişim kapalı), AES256 yükleme, çalışma grubu (sonuç yeri zorunlu, 100 MB tarama sınırı), veritabanı, tablo tanımı ve satır sayısı; tekrar çalıştırmak güvenli
  - _Gereksinimler: 1.1, 1.2, 1.4, 1.5, 4.1–4.3_
- [x] 3. Kişisel veri dışarıda: kurye adı ve `notes.json` yüklenmez; `test_athena_setup.py` (4 test)
  - _Gereksinimler: 3.1–3.3_
- [x] 4. `cm/athena.py`: `validate_sql` (tek SELECT, 200 satır), `run_query` (60 sn, durdurma), `query_history` (JSON ya da açıklayıcı hata; AWS ayrıntısı log'da)
  - _Gereksinimler: 5.1–5.7_
- [x] 5. Analiz Ajanı: `analyst` rolü (`cm/roles.py`), şemalı istem (`cm/prompt.py`), Supervisor'da `ask_analyst`; `query_history` ve `ask_analyst` müdür aracı (`cm/scope.py`)
  - _Gereksinimler: 6.1–6.5_
- [x] 6. `agentcore_config.py`: `analyst` runtime'ı, `CM_ATHENA_DATABASE` / `CM_ATHENA_WORKGROUP`, `analyst-policy.json`; tek runtime'da Athena yok
  - _Gereksinimler: 6.6, 7.1–7.5_
- [x] 7. Testler: `deploy/agentcore/tests/test_athena.py` (24 test; sahte Athena istemcisi ve saat), `test_agentcore_config.py` analist testi
  - _Gereksinimler: 5.2–5.7, 6.1, 6.2, 6.5, 7.1_
- [x] 8. Kurulum hesapta: `AWS_PROFILE=… AWS_REGION=us-east-1 python deploy/athena/athena_setup.py`; dört tablonun satır sayısı yazdırılır (`deliveries` 92.381, `addresses` 40.000)
  - _Gereksinimler: 1.1–1.5, 2.5_
- [ ] 9. Dağıtılmış Analiz Ajanı: `agentcore invoke --runtime analyst` ile MUDUR-01 "A ve D yapısında gün gün başarısız teslim"; sorgu tek satırda belirtilir, sayılar `daily_metrics` ile aynı
  - _Gereksinimler: 5.4, 6.1–6.3_
- [ ] 10. Supervisor üzerinden: MUDUR-01'in geçmiş veri sorusu `ask_analyst`'e gider; O02'nin aynı sorusu uzman çağrılmadan reddedilir; çalışma grubunda taranan veri 100 MB'ın altında
  - _Gereksinimler: 4.3, 6.4, 6.5_
