---
inclusion: always
---
# AgentCore: bu projede dağıtım kuralları

Bu dosya Courier Memory ajanlarının AgentCore Runtime'a dağıtımına özgü kararları söyler.

## Sabitler

| Ne | Değer |
|---|---|
| Proje adı | `CourierMemory` |
| İskele | `agentcore create --name CourierMemory --template agent-python-strands`, `$CM_WORKSPACE` içinde (varsayılan: reponun üst klasörü, yani `../CourierMemory`). Klasör yapısı elle kurulmaz |
| Çalışma ortamları | `agent` (Supervisor; şablonun adı, `agentcore invoke --runtime agent`) + `planner`, `courier`, `memory_keeper`, `analyst`. CDK adı `<Proje>_<hedef>_<rol>` (ör. `CourierMemory_default_planner`) |
| Rol seçimi | `CM_AGENT_ROLE` (`supervisor` \| `planner` \| `courier` \| `memory_keeper` \| `analyst` \| `all`); `agentcore.json`'a `deploy/agentcore/agentcore_config.py` yazar |
| Tek runtime | `CM_MULTI_AGENT=0 deploy/agentcore/bootstrap.sh` → yalnız `agent`, on alan aracı, Athena yok |
| Kodun kaynağı | Bu repoda `deploy/agentcore/runtime/` + `agents/` + `sim/cm_sim/` + `data/`. Projeye `deploy/agentcore/bootstrap.sh` kopyalar; beş runtime aynı `app/agent` klasöründen dağıtılır |
| Hafıza | Şablonun tanımladığı `agentMemory` (SEMANTIC + EPISODIC) korunur ve her runtime'a bağlanır; ikinci hafıza açılmaz |
| Gözlemlenebilirlik | `agentcore/agentcore.json` → her runtime'ın `envVars` listesinde `UNIFIED_TRACES_DESTINATION_ENABLED = "true"` |
| Model | `global.anthropic.claude-sonnet-5` (`CM_AGENT_MODEL_ID`; `bootstrap.sh` şablonun `model/load.py` dosyasına yazar). Test ve demo Opus ile yapılmaz |
| Yerel port | `agentcore dev --port 8081` (8000 yerel API'nindir) |

## Dağıtımın üç şartı (her spec ve plan bunları içermeli)

1. **Deploy:** proje `agentcore create` ile kurulur, `agentcore deploy` ile AgentCore Runtime'a dağıtılır (elle ya da CI'dan: `aws-dagitim` spec'i).
2. **Observability:** yukarıdaki `envVars` girdisi, her runtime'da.
3. **Tool:** ajan en az bir araç açar. Bizde on alan aracı (`deploy/agentcore/runtime/cm/tools.py`), Analiz Ajanı'nın `query_history`'si (`cm/athena.py`) ve Supervisor'ın dört yönlendirme aracı (`cm/roles.py`) var; çekirdek takımda altı alan aracı çalışır.

Kontrol: `deploy/agentcore/verify.sh` (yerel) ve `deploy/agentcore/verify.sh CourierMemory --deployed` (üç şart).

## Çok ajanlı yapı

| Runtime | Ajan | Araçlar | Kim |
|---|---|---|---|
| `agent` | Supervisor | `ask_planner`, `ask_courier_agent`, `ask_memory_keeper`, `ask_analyst` | herkes (uzmana göre erken ret) |
| `planner` | Planlama Ajanı | `plan_day`, `morning_review`, `region_report` | müdür |
| `courier` | Kurye Ajanı | `courier_briefing`, `stop_cards`, `approaching_stop` | kurye (yalnız kendisi), müdür |
| `memory_keeper` | Hafıza Ajanı | `leave_note`, `branch_memory_summary`, `real_day_evidence`, `harvest_questions` | araca göre |
| `analyst` | Analiz Ajanı | `query_history` (Athena, salt okunur; `athena-analiz` spec'i) | müdür |

- **Supervisor alan aracı taşımaz.** Uzmanı `InvokeAgentRuntime` ile çağırır (`cm/delegate.py`), ARN'yi `CM_RUNTIME_PREFIX` + rol adıyla `ListAgentRuntimes`'tan bulur; tek `agentcore deploy` yeter. Yeniden deneme yoktur (`leave_note` yazma işlemidir).
- **Yeni alan aracı** tek bir uzmana girer: `cm/roles.py → SPECIALIST_TOOLS` ve `cm/tools.py` içinde `COURIER_TOOLS` / `MANAGER_TOOLS` / `PUBLIC_TOOLS` listelerinden birine; uzmanın istem bölümüne (`cm/prompt.py → AGENT_SECTIONS`) bir satır. Listeye girmeyen araç herkese açık olur.
- **Yeni uzman** eklenirse: `SPECIALIST_TOOLS`, `agentcore_config.py → SPECIALISTS`, Supervisor'a bir `ask_*` aracı, `AGENT_SECTIONS` ve gerekiyorsa `cm/scope.py`'de erken ret.
- Her uzman kendi oturumunu tutar (`<oturum>-<rol>`, ≥ 33 karakter). Uzman doğrudan da çağrılabilir: `agentcore invoke --runtime planner --payload '{"prompt":"…","actorId":"MUDUR-01"}'`.
- Bedeli: Supervisor üzerinden her istek en az iki model çağrısıdır (Supervisor + uzman).

## Kimlik

- İstek gövdesi `{"prompt", "actorId", "day"?}`. `actorId` kurye kimliği (ör. `O02`), müdür (`MUDUR-…`) ya da yoksa konuk (`default`). Amazon Quick köprüsü her soruyu sabit `MUDUR-QUICK` kimliğiyle gönderir (`quick-koprusu` spec'i).
- **Kimlik modelden gelmez.** Supervisor'ın `ask_*` araçlarında kimlik ve oturum kapanıştadır; modelin gördüğü şemada yalnız `question` ve `day` vardır. Uzmana isteğin `actorId`'si gider.
- **Kimlik sınırı koddadır, istemde değil:** `cm/scope.py` içindeki `BeforeToolCallEvent` kancası başka kuryenin verisini isteyen araç çağrısını iptal eder. Her uzman sınırı kendisi uygular; Supervisor'daki ret (`ask_planner`, `ask_analyst` yalnız müdür; `ask_courier_agent` kimlik ister) yalnız boşa runtime ve model çağrısını önler.

## Kod kuralları

- **Düzenleme yeri repodur, proje değil.** `../CourierMemory/app/agent/` altındaki `cm/`, `agents/`, `cm_sim/`, `data/` kopyadır; `bootstrap.sh` her çalıştığında üzerine yazar. Değişikliği `deploy/agentcore/runtime/` ya da `agents/` içinde yap, sonra `bootstrap.sh` + `agentcore deploy`.
- `main.py`: `from bedrock_agentcore.runtime import BedrockAgentCoreApp` (kökten içe aktarma yok), ajan `_get_agent` içinde kimlik + oturum başına tembel kurulur, işleyici `@app.entrypoint` ile akış döndüren asenkron üreteç, `app.run()` yalnız `__main__` altında. İz öznitelikleri: `cm.agent_role`, `cm.actor_role`, `cm.actor_id`, `cm.toolset`.
- **LLM karar verir, hesap araçta** (`tech.md`): araçlar ince sarmalayıcıdır; hesabı `cm/backend.py` yapar ve JSON metni döner. Model sayı üretmez. Analiz Ajanı SQL'i yazar, sayıyı Athena hesaplar.
- **İki araç takımı:** tam (`agents.Services`, 10 araç) ve çekirdek (`cm/core.py`, yalnız `data/demo_run` ve standart kütüphane, 6 araç). `CM_TOOLSET=auto` alan kodu yüklenemezse çekirdeğe düşer. `agents/memory.py` anahtar kelimeleri ya da kart kuralları değişirse `cm/core.py` de güncellenir (eşitlik testi kırılır).
- **Model kimliği çıkarım profili biçiminde** (`global.anthropic…`). Öneksiz kimlik dağıtılmış ajanda hata verir. Güncel kimliği `aws bedrock list-foundation-models --by-provider Anthropic` ile bul; `CM_AGENT_MODEL_ID` ile ver, `bootstrap.sh` `app/agent/model/load.py`'ye yazar.
- **Bağımlılık:** `app/agent/pyproject.toml` → `[project].dependencies` yalnız çalışma zamanı paketleri (numpy, scipy, pydantic, pyyaml; hepsinin ARM64 tekerleği var). `pytest` oraya girmez.
- Alt ajanlar (Orkestratör, Atama, Brifing, Hafıza, Değerlendirme, Bölge, Hasat) çalışma ortamında kurallı yolda çalışır (`CM_LLM_MODE=mock`); kararı ve anlatımı runtime ajanları yapar.

## İzin (en az yetki)

- İzin `agentcore.json` → `additionalPolicies` ile verilir; IAM rolü elle düzenlenmez. Politikaları `agentcore_config.py` `agentcore/` klasörüne yazar.
- `agent` (Supervisor): `supervisor-policy.json` → `bedrock-agentcore:InvokeAgentRuntime` yalnız `runtime/<Proje>_<hedef>_*`, ayrıca `ListAgentRuntimes` (kaynak düzeyinde kısıtlanamaz).
- `analyst`: `analyst-policy.json` → Athena yalnız `courier-memory` çalışma grubunda; Glue yalnız `courier_memory` okuma; S3 `courier-memory-athena-*/data/*` okuma, `results/*` yazma.
- `planner`, `courier`, `memory_keeper`: ek izin yok. AWS API'si çağıran yeni bir araç eklenirse (DynamoDB, Knowledge Base) yalnız o uzmana, `agentcore_config.py` içinde ayrı bir politika dosyasıyla verilir.
- Kullanıcının `agent`'a eklediği `envVars` ve politikalar uzmanlara da geçer; yönetilen girdiler her çalıştırmada yeniden yazılır, yinelenmez.

## Bilinen sınır

Şubenin adres hafızası (`MemoryBook`) çalışma ortamında oturumun geçici dosyasındadır ve her runtime'ın kendi kopyası vardır: not `memory_keeper`'da yazılır, kartları `courier` okur. Çok ajanlı yapıda oturumda bırakılan not Kurye Ajanı'nın kartlarına kalıcı depo gelene dek yansımaz; tek runtime'da (`CM_MULTI_AGENT=0`) aynı oturumda kartta görünür. Yeni oturum demo tohumundan başlar. Kalıcı depo (DynamoDB tablosu, AgentCore Gateway hedefi olarak) `agentcore-runtime` spec'inde sonraki adım olarak tanımlıdır; web uygulamasının DynamoDB deposu `aws-dagitim` spec'indedir. Konuşma hafızası (kim ne söyledi) AgentCore Memory'dedir ve oturumlar arası kalıcıdır. Athena verisi `data/demo_run`'ın kopyasıdır; yeniden üretimden sonra `deploy/athena/athena_setup.py` yeniden çalıştırılır.
