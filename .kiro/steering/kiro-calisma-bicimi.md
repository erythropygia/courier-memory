---
inclusion: always
---
# Kiro ile çalışma biçimi

Bu repo Kiro'nun spec odaklı akışıyla geliştirilir. Kod yazmadan önce niyet yazılır, onaylanır, sonra görevler tek tek yürütülür.

## Spec

- Her özellik için `.kiro/specs/<özellik>/`: `requirements.md` (kullanıcı hikayesi + sınanabilir kabul kriterleri), `design.md` (teknik yaklaşım), `tasks.md` (sıralı görevler, her biri karşıladığı gereksinime bağlı).
- Yeni spec'lerde kabul kriterleri EARS kalıbındadır: **WHEN** <koşul> **THE SYSTEM SHALL** <davranış>; istenmeyen durum için **IF** <durum> **THEN THE SYSTEM SHALL** <davranış>.
- Görev bitince `tasks.md` içinde `[x]` yapılır. Yapılmamış iş `[ ]` kalır; "sonra yaparız" diye işaretlenmez.
- Kod değişikliği olmayan işler (dağıtılmış ajanı sınamak, log okumak) spec gerektirmez; komutu çalıştır ya da Kiro'ya sor.
- Mevcut spec'ler: `dunya-simulator`, `ajanlar`, `orkestrator`, `ekonomi`, `sabah-akisi`, `api-arayuz`, `durak-kartlari`, `oz-degerlendirme-bolge`, `gercek-gun`, `akis-arayuzu`, `agentcore-runtime`, `athena-analiz`, `quick-koprusu`, `aws-dagitim`.

## Steering, skill, hook, MCP

| Araç | Yer | Ne zaman |
|---|---|---|
| Steering | `.kiro/steering/*.md` | Her oturumun başında okunur: ürün, teknik kurallar, veri ve KVKK, sunum dili, repo yapısı, AgentCore |
| Skill | `.kiro/skills/<ad>/SKILL.md` | İstenince (`/` ile ya da doğal dille): AgentCore'a dağıtım, dağıtım kontrolü, demo provası, yeni hafıza türü |
| Hook | `.kiro/hooks/*.kiro.hook` | Dosya kaydedilince: testler, veri kuralı denetimi, AgentCore kopyasının eskidiği uyarısı, sözleşme belgesi eşitleme |
| MCP | `.kiro/settings/mcp.json` | `courier-memory` sunucusu: şube hafızası ve demo verisi, salt okunur (`deploy/mcp/cm_mcp_server.py`) |

## Her değişiklikte

1. İlgili spec'in görevini aç; yoksa önce spec.
2. Kod İngilizce, kullanıcıya görünen metin Türkçe (`structure.md` → Adlandırma, `sunum-dili.md`).
3. Test: `PYTHONUTF8=1 pytest -q` (hızlı takım). Yeni davranış test olmadan bitmiş sayılmaz.
4. API değiştiyse `docs/sozlesmeler.md`.
5. AgentCore'a giden kod değiştiyse `deploy/agentcore/bootstrap.sh` + `agentcore deploy` + `verify.sh --deployed`.
