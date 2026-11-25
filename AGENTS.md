# Courier Memory: ajanlar ve inceleyenler için kılavuz

> **In one paragraph (English summary).** Courier Memory turns the unwritten address knowledge of last-mile couriers into a shared branch memory and gives it to a courier who does not know the area, at the right moment. It is built spec-first with **Kiro** (11 specs, steering, skills, hooks, a project MCP server) and ships a **Strands** agent to **Amazon Bedrock AgentCore Runtime** with nine `@tool` functions, per-courier identity scoping enforced in code, **AgentCore Memory**, and OpenTelemetry traces to CloudWatch. The evidence table below points to the exact files.

## Nereden başlanır

| Soru | Yer |
|---|---|
| Ürün ne, kime, neden | `.kiro/steering/product.md` |
| Hangi özellik nasıl tanımlandı ve yapıldı | `.kiro/specs/<özellik>/` (`requirements.md`, `design.md`, `tasks.md`) |
| AgentCore'da ne çalışıyor | `deploy/agentcore/` + `.kiro/specs/agentcore-runtime/` |
| Parçalar arası sözleşme (API, veri biçimleri) | `docs/sozlesmeler.md` |

## Kullanılan özellikler ve kanıtı

### Kiro

| Özellik | Kanıt |
|---|---|
| **Specs** (gereksinim → tasarım → görev) | `.kiro/specs/` altında 11 spec: `dunya-simulator`, `ajanlar`, `orkestrator`, `ekonomi`, `sabah-akisi`, `api-arayuz`, `durak-kartlari`, `oz-degerlendirme-bolge`, `gercek-gun`, `akis-arayuzu`, `agentcore-runtime`. Yeni spec'lerde kabul kriterleri EARS kalıbında; görevler gereksinim numarasına bağlı |
| **Steering** (her oturumda okunan kurallar) | `.kiro/steering/`: `product`, `tech`, `structure`, `veri-kurallari`, `sunum-dili`, `agentcore`, `kiro-calisma-bicimi` (hepsi `inclusion: always`) |
| **Skills** (istenince çalışan yönergeler) | `.kiro/skills/`: `deploy-courier-memory`, `verify-deployment`, `demo-prova`, `yeni-hafiza-turu` |
| **Hooks** (kaydetmede otomasyon) | `.kiro/hooks/`: testler, veri ve KVKK denetimi, AgentCore kopyası uyarısı, sözleşme eşitleme, AgentCore şartlarını koruma |
| **MCP** | `.kiro/settings/mcp.json` → `deploy/mcp/cm_mcp_server.py` (projenin kendi sunucusu: şube hafızası, salt okunur, 5 araç). |

### Amazon Bedrock AgentCore

| Özellik | Kanıt |
|---|---|
| **Runtime** | `deploy/agentcore/runtime/main.py` (`BedrockAgentCoreApp`, tembel `_get_agent`, akış döndüren `@app.entrypoint`); iskele `agentcore create` ile, yerleştirme `deploy/agentcore/bootstrap.sh` |
| **Araçlar** (Strands `@tool`) | `deploy/agentcore/runtime/cm/tools.py`: 9 araç, deterministik alan fonksiyonlarını çağırır. İki arka uç (`cm/backend.py`): tam (`agents.Services`) ve çekirdek (`cm/core.py`, yalnız veri dosyaları; alan kodu yüklenemezse otomatik düşüş) |
| **Memory** | `deploy/agentcore/runtime/cm/memory.py`: şablonun `agentMemory` hafızası, ad alanları `actorId` ile ayrılır |
| **Kimlik sınırı** | `deploy/agentcore/runtime/cm/scope.py`: `BeforeToolCallEvent` kancası; kurye yalnız kendi verisi, müdür araçları yalnız müdür, konuk yalnız herkese açık araçlar |
| **Observability** | `UNIFIED_TRACES_DESTINATION_ENABLED=true` (`bootstrap.sh` yazar, `verify.sh` denetler); izlerde `cm.actor_role`, `cm.actor_id` |
| **Gateway**, **sohbet arayüzü (ECS Fargate)** | Sonraki adımlar: spec `agentcore-runtime` gereksinim 9–10, görev 15–16 (yapılmadı) |

### Amazon Bedrock

| Özellik | Kanıt |
|---|---|
| Claude, çıkarım profili kimliğiyle | `deploy/agentcore/runtime/cm/model.py` (AgentCore ajanı) · `agents/llm.py` `CM_BEDROCK_CLIENT=invoke` (yerel API) |
| Araç kullanan beş alan ajanı + iki yeni ajan | `agents/orchestrator.py`, `assignment.py`, `memory.py`, `briefing.py`, `harvest.py`, `review.py`, `region_agent.py`; her biri canlı yol + aynı araçlarla kurallı yedek |
| Kayıt-oynat güvencesi | `agents/llm.py`: `mock / live / record / replay` |

## Bu repoda çalışırken

- **Kod İngilizce, kullanıcıya görünen metin Türkçe.** Terim sözlüğü: `.kiro/steering/structure.md` → Adlandırma.
- **LLM karar verir, hesap araçta.** Sayı üreten her şey deterministik Python'dur (`.kiro/steering/tech.md`).
- **Kişisel veri ve kapı şifresi kaydedilmez, söylenmez.** Hafıza kişiyi değil adresi anlatır (`.kiro/steering/veri-kurallari.md`).
- **Önce spec.** Yeni özellik `.kiro/specs/<özellik>/` olmadan başlamaz; biten görev `tasks.md` içinde işaretlenir, yapılmamış iş işaretsiz kalır.
- **Test:** `PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q` (AWS gerekmez).
- **AgentCore'a giden kod repoda düzenlenir**, projedeki kopya değil: `deploy/agentcore/bootstrap.sh` → `agentcore deploy` → `deploy/agentcore/verify.sh CourierMemory --deployed`.
