---
inclusion: always
---
# AgentCore: bu projede dağıtım kuralları

Genel AgentCore ve Strands kuralları atölyenin steering dosyalarındadır (`agentcore-deployment.md`, `strands-agent-coding.md`; Getting Started adımında çalışma alanına yazılır). Çelişki olursa **onlar geçerlidir**. Bu dosya yalnız projeye özgü kararları söyler.

## Sabitler

| Ne | Değer |
|---|---|
| Proje adı | `CourierMemory` (`CustomerServiceAgent` olamaz) |
| İskele | `agentcore create --name CourierMemory --template agent-python-strands`, `~/environment` içinde. Klasör yapısı elle kurulmaz |
| Çalışma ortamı adı | `agent` (şablonun adı; `agentcore invoke --runtime agent`) |
| Kodun kaynağı | Bu repoda `deploy/agentcore/runtime/` + `agents/` + `sim/cm_sim/` + `data/`. Projeye `deploy/agentcore/bootstrap.sh` kopyalar |
| Hafıza | Şablonun tanımladığı `agentMemory` (SEMANTIC + EPISODIC) korunur; ikinci hafıza açılmaz |
| Gözlemlenebilirlik | `agentcore/agentcore.json` → runtime `envVars` içinde `UNIFIED_TRACES_DESTINATION_ENABLED = "true"` |
| Yerel port | `agentcore dev --port 8081`. 8080 Kiro IDE Browser'ındır: kullanma, durdurma |

## Lab 7'nin üç şartı (her spec ve plan bunları içermeli)

1. **Deploy:** proje `agentcore create` ile kurulur, `agentcore deploy` ile AgentCore Runtime'a dağıtılır.
2. **Observability:** yukarıdaki `envVars` girdisi.
3. **Tool:** ajan en az bir araç açar. Bizde dokuz Strands `@tool` var (`deploy/agentcore/runtime/cm/tools.py`); çekirdek takımda altısı çalışır.

Kontrol: `deploy/agentcore/verify.sh` (yerel) ve `deploy/agentcore/verify.sh CourierMemory --deployed` (üç şart).

## Kod kuralları

- **Düzenleme yeri repodur, proje değil.** `~/environment/CourierMemory/app/agent/` altındaki `cm/`, `agents/`, `cm_sim/`, `data/` kopyadır; `bootstrap.sh` her çalıştığında üzerine yazar. Değişikliği `deploy/agentcore/runtime/` ya da `agents/` içinde yap, sonra `bootstrap.sh` + `agentcore deploy`.
- `main.py`: `from bedrock_agentcore.runtime import BedrockAgentCoreApp` (kökten içe aktarma yok), ajan `_get_agent` içinde tembel kurulur, işleyici `@app.entrypoint` ile akış döndüren asenkron üreteç, `app.run()` yalnız `__main__` altında.
- İstek gövdesi `{"prompt", "actorId", "day"?}`. `actorId` kurye kimliği (ör. `O02`), müdür (`MUDUR-…`) ya da yoksa konuk (`default`).
- **Kimlik sınırı koddadır, istemde değil:** `cm/scope.py` içindeki `BeforeToolCallEvent` kancası başka kuryenin verisini isteyen araç çağrısını iptal eder. Yeni araç eklerken `COURIER_TOOLS` / `MANAGER_TOOLS` / `PUBLIC_TOOLS` listelerinden birine koy; listeye girmeyen araç herkese açık olur.
- **LLM karar verir, hesap araçta** (`tech.md`): araçlar ince sarmalayıcıdır; hesabı `cm/backend.py` yapar ve JSON metni döner. Model sayı üretmez.
- **İki araç takımı:** tam (`agents.Services`, 9 araç) ve çekirdek (`cm/core.py`, yalnız `data/demo_run` ve standart kütüphane, 6 araç). `CM_TOOLSET=auto` alan kodu yüklenemezse çekirdeğe düşer. `agents/memory.py` anahtar kelimeleri ya da kart kuralları değişirse `cm/core.py` de güncellenir (eşitlik testi kırılır).
- **Model kimliği çıkarım profili biçiminde** (`global.anthropic…`). Öneksiz kimlik dağıtılmış ajanda hata verir. Güncel kimliği `aws bedrock list-foundation-models --by-provider Anthropic` ile bul; `app/agent/model/load.py` içinde tut.
- **Bağımlılık:** `app/agent/pyproject.toml` → `[project].dependencies` yalnız çalışma zamanı paketleri (numpy, scipy, pydantic, pyyaml; hepsinin ARM64 tekerleği var). `pytest` oraya girmez.
- **İzin:** araçlar bugün AWS API'si çağırmaz. Çağıran bir araç eklenirse (DynamoDB, Knowledge Base) izin `agentcore.json` → `additionalPolicies` ile verilir; IAM rolü elle düzenlenmez.
- Alt ajanlar (Orkestratör, Brifing, Hafıza, Değerlendirme, Bölge) çalışma ortamında kurallı yolda çalışır (`CM_LLM_MODE=mock`); kararı ve anlatımı Strands ajanı yapar.

## Bilinen sınır

Şubenin adres hafızası (`MemoryBook`) çalışma ortamında oturumun geçici dosyasındadır: aynı oturumda bırakılan not aynı oturumda kartta görünür, yeni oturum demo tohumundan başlar. Kalıcı depo (DynamoDB tablosu, AgentCore Gateway hedefi olarak) `agentcore-runtime` spec'inin esnetme hedefidir. Konuşma hafızası (kim ne söyledi) AgentCore Memory'dedir ve oturumlar arası kalıcıdır.
