# Tasarım: Athena analizi ve Analiz Ajanı

## Genel bakış

```
data/demo_run (delivery_log, addresses, daily + meta, couriers)
   │  deploy/athena/athena_setup.py  (bir kez; tekrar çalıştırmak güvenli)
   ▼
S3  courier-memory-athena-<hesap>-<bölge>
   ├─ data/<tablo>/part-0.json.gz     JSON Lines, AES256
   └─ results/                        sorgu sonuçları (çalışma grubu zorlar)
Glue/Athena  veritabanı courier_memory: deliveries · addresses · daily_metrics · couriers
             çalışma grubu courier-memory: sorgu başına ≤ 100 MB tarama
   ▲
   │  StartQueryExecution / GetQueryExecution / GetQueryResults
AgentCore runtime "analyst"  (CM_AGENT_ROLE=analyst)
   query_history(sql) ── validate_sql → "SELECT * FROM (<sql>) AS q LIMIT 200" → bekle (≤ 60 sn) → JSON
   ▲
   │  ask_analyst(question, day?)    kimlik kapanışta; kurye/konuk erken ret
Supervisor "agent"  ◄── müdür (MUDUR-…, Amazon Quick köprüsünden MUDUR-QUICK)
```

Model soruyu SQL'e çevirir ve sonucu anlatır; sayı Athena'dan gelir. Analiz verisi `data/demo_run`'ın bir anlık kopyasıdır: çalışma ortamının canlı adres hafızası buraya yazılmaz.

## Dosyalar

| Dosya | Ne |
|---|---|
| `deploy/athena/athena_setup.py` | `TABLES` (sütunlar ve yorumlar), `build_rows(tablo, run)` (saf), `create_table_sql`, `_jsonl_gz`; AWS: bucket, çalışma grubu, yükleme, DDL, satır sayısı |
| `deploy/agentcore/runtime/cm/athena.py` | `SCHEMA` (istem metni), `validate_sql`, `run_query(sql, client, sleep, now)` (sınanabilir), `query_history` aracı; `QueryRejected`, `QueryFailed` |
| `deploy/agentcore/runtime/cm/roles.py` | `SPECIALIST_TOOLS["analyst"] = (query_history,)`; Supervisor'da `ask_analyst` |
| `deploy/agentcore/runtime/cm/prompt.py` | `AGENT_SECTIONS["analyst"]`: görev + `SCHEMA` |
| `deploy/agentcore/runtime/cm/scope.py` | `query_history`, `ask_analyst` → müdür araçları |
| `deploy/agentcore/agentcore_config.py` | `analyst` runtime'ı, `CM_ATHENA_DATABASE`, `CM_ATHENA_WORKGROUP`, `analyst_policy()` → `agentcore/analyst-policy.json` |
| `deploy/athena/tests/test_athena_setup.py`, `deploy/agentcore/tests/test_athena.py` | AWS'ye gitmeyen testler |

## Tablolar

| Tablo | Kaynak dosya | Satır (demo) | Sütunlar |
|---|---|---|---|
| `deliveries` | `delivery_log.json` | 92.381 | `day`, `address_id`, `minute`, `absent` |
| `addresses` | `addresses.json` | 40.000 | `id`, `lat`, `lng`, `kind`, `block`, `label` |
| `daily_metrics` | `daily.json` + `meta.json` (`arm_label`) | 4 yapı × gün | `arm`, `arm_label`, `day`, `weekday`, gönderi ve deneme sayıları, `fail` ve yedi `fail_<neden>`, `first_attempt_rate`, `preventable_fail`, km, süre, bant ve fazla mesai, `unfamiliar_share`, ipucu ve hafıza ölçüleri, `wasted_trips`, `eta_abs_error` … |
| `couriers` | `couriers.json` | kadro | `id`, `kind`, `start_day`, `end_day`, `leave_day_count` |

- Satırlar tablonun sütun sırasıyla üretilir; eksik alan `null` olur. `fail_<neden>` sütunları `fail_by_reason`'dan açılır.
- Yüklenmeyenler: kurye adı, `notes.json` (serbest metin), `leave_days` listesinin kendisi (yalnız sayısı).

## Koruma katmanları

| Katman | Ne yapar | Nerede |
|---|---|---|
| 1. SQL denetimi | Tek `SELECT` / `WITH`; `;`, `--`, `/*` yok; yazma ve yönetim anahtar kelimeleri yok; yalnız `courier_memory` tabloları; sonuç `LIMIT 200` ile sarılır | `cm/athena.py → validate_sql` |
| 2. Çalışma grubu | Sonuç yeri zorunlu (`EnforceWorkGroupConfiguration`), sorgu başına ≤ 100 MB tarama, CloudWatch ölçüleri | `athena_setup.py → _ensure_workgroup` |
| 3. IAM | Athena yalnız bu çalışma grubunda; Glue yalnız okuma; S3 `data/` okuma, `results/` yazma | `agentcore_config.py → analyst_policy` |

Katmanlar birbirinin yedeğidir: denetim boşa Athena çağrısını önler ve modele erken, okunur bir neden verir; denetim bir gün aşılsa da çalışma grubu büyük taramayı, IAM yazmayı engeller.

## Araç akışı

```
query_history(sql)
  validate_sql ── QueryRejected → {"error", "hint": "Yalnız tek bir SELECT yazın."}
  start_query_execution(QueryString, Database, WorkGroup)
  her 1 sn get_query_execution
     SUCCEEDED → get_query_results(MaxResults=201) → {columns, rows, row_count, truncated, scanned_kb}
     FAILED / CANCELLED → QueryFailed (Athena'nın nedeni) → {"error"}
     60 sn aşıldı → stop_query_execution → QueryFailed → {"error"}
  AWS istemci hatası → log (ayrıntı) · modele "Athena'ya şu an ulaşılamıyor (<kod>)"
```

## İzin politikası (`agentcore/analyst-policy.json`)

| Sid | Eylem | Kaynak |
|---|---|---|
| `RunQueries` | `athena:StartQueryExecution`, `GetQueryExecution`, `GetQueryResults`, `StopQueryExecution`, `GetWorkGroup` | `workgroup/courier-memory` |
| `ReadCatalog` | `glue:GetDatabase`, `GetTable`, `GetTables`, `GetPartition`, `GetPartitions` | katalog, `database/courier_memory`, `table/courier_memory/*` |
| `ReadData` | `s3:GetObject` | `courier-memory-athena-*/data/*` |
| `ListBucket` | `s3:ListBucket`, `s3:GetBucketLocation` | `courier-memory-athena-*` |
| `WriteResults` | `s3:PutObject`, `s3:GetObject`, `s3:AbortMultipartUpload` | `courier-memory-athena-*/results/*` |

## Test

- `deploy/athena/tests/test_athena_setup.py` (4 test): her tablonun satırları sütun sırasına uyar ve JSON'a çevrilir; satır sayıları ve neden toplamı; kurye adı ve not tablosu yok; DDL tablo önekini gösterir.
- `deploy/agentcore/tests/test_athena.py` (24 test, parametreli): kabul edilen ve reddedilen sorgular, çalışma grubu ve veritabanı, SQL hatası ve zaman aşımı (sahte istemci, sahte saat), aracın JSON ya da açıklayıcı hata dönmesi, kimlik sınırı (analiz ve hasat yalnız müdür), analist runtime'ının tek araç ve şemalı istemle kurulması; aynı dosyada `harvest_questions` testleri (`agentcore-runtime` Gereksinim 16).
- `deploy/agentcore/tests/test_agentcore_config.py::test_analyst_gets_athena_env_and_read_only_policy`.

## Açık riskler

- Athena verisi `data/demo_run`'ın kopyasıdır: yeniden üretimden (`cm_sim.run --demo` → `cm_sim.publish`) sonra `athena_setup.py` yeniden çalıştırılmazsa ajan eski sayıları söyler.
- Tablo tanımı her kurulumda silinip yeniden kurulur; kurulum sırasında gelen sorgu "tablo yok" hatası alabilir.
- `daily_metrics` dört yapıyı yan yana tutar; model yapıyı (`arm`) filtrelemeyi unutursa sayılar karışır. İstem yapıların anlamını söyler; sonuç sorguyla birlikte anlatılır.
- Kurulum ve canlı sorgu henüz dağıtım hesabında yapılmadı.
