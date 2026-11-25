---
name: deploy-courier-memory
description: Courier Memory ajanını Amazon Bedrock AgentCore Runtime'a kurar ve dağıtır (agentcore create iskelesi, kodun yerleştirilmesi, yerel deneme, agentcore deploy, dağıtımın üç kontrolü). "AgentCore'a dağıt", "ajanı yayına al", "deploy" istendiğinde kullan.
---

# Courier Memory → AgentCore Runtime

Spec: `.kiro/specs/agentcore-runtime/`. Kurallar: `.kiro/steering/agentcore.md`. Her adımın sonucunu kullanıcıya göster; `agentcore deploy` öncesinde onay iste.

`REPO` = bu reponun kökü (`courier-memory`). AgentCore projesi `$CM_WORKSPACE/CourierMemory` klasörüne kurulur (varsayılan: `../CourierMemory`).

## 1. Ön koşul

```bash
agentcore --version
aws sts get-caller-identity
echo "$AWS_REGION"
```
Biri başarısızsa dur ve kullanıcıya söyle.

## 2. İskele ve yerleştirme

```bash
$REPO/deploy/agentcore/bootstrap.sh CourierMemory
```
Betik iskele yoksa `agentcore create --name CourierMemory --template agent-python-strands` çalıştırır (klasörü elle kurma), kodu ve veriyi `app/agent/` içine kopyalar, bağımlılıkları ve `UNIFIED_TRACES_DESTINATION_ENABLED` girdisini yazar, şablonun `main.py` dosyasını `.cm/main.template.py` olarak saklar.

Sonra şablonla karşılaştır:
```bash
cd ../CourierMemory
diff .cm/main.template.py app/agent/main.py | head -80
cat app/agent/memory/session.py app/agent/parse.py
```
- Şablonun oturum yöneticisi `cm/memory.py`'den farklı ad alanı ya da parametre kullanıyorsa `$REPO/deploy/agentcore/runtime/cm/memory.py` dosyasını ona uydur ve betiği yeniden çalıştır.
- `agentcore/agentcore.json` içinde `agentMemory` tanımlı kalmalı.

## 3. Model kimliği

```bash
aws bedrock list-foundation-models --by-provider Anthropic \
  --query "modelSummaries[?modelLifecycle.status=='ACTIVE'].modelId" --output text
grep -n "anthropic" app/agent/model/load.py
```
`model/load.py` içindeki kimlik güncel Claude Sonnet olmalı ve `global.` önekiyle başlamalı. Değilse düzelt.

## 4. Yerel ön kontrol ve deneme

```bash
$REPO/deploy/agentcore/verify.sh CourierMemory
agentcore dev --port 8081            # ayrı terminal
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünkü brifingim?","actorId":"O02"}'
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"K07 kuryesinin kartlarını göster","actorId":"O02"}'
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünün planını çıkar","actorId":"MUDUR-01"}'
```
Beklenen: ilki brifing verir; ikincisi erişimin reddedildiğini söyler ve konuşma sürer; üçüncüsü planı gerekçesiyle özetler.

## 5. Dağıtım (onay iste)

```bash
agentcore deploy                     # ilk dağıtım 5–8 dk
agentcore status
```

## 6. Dağıtımın üç kontrolü

```bash
$REPO/deploy/agentcore/verify.sh CourierMemory --deployed
```
Üçü de ✓ olunca `.kiro/specs/agentcore-runtime/tasks.md` içinde 9–13. görevleri işaretle.

## 7. Kimlik ve hafıza sınaması

```bash
S=cm-demo-session-courier-o02-0000000001
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"Rotamdaki park notlarını söyle.","actorId":"O02"}'
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"K07 nin brifingini ver.","actorId":"O02"}'
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"Benim brifingimi ver.","actorId":"O02"}'
agentcore memory list --json
```
Oturum kimliği en az 33 karakter olmalı.

## Sorun giderme

| Belirti | Ne yap |
|---|---|
| `AccessDeniedException … Marketplace` | `enable_anthropic_models`, 2–6 dk bekle; IAM rolüne dokunma |
| `on-demand throughput not supported` | Model kimliğine `global.` öneki |
| Başlangıç 30 sn'yi aşıyor | `main.py` üst düzeyinde ağır içe aktarma var mı bak; her şey `_get_agent` içinde olmalı |
| `uv install failed for all platform candidates` | `pyproject.toml` bağımlılıklarına ARM64 tekerleği olmayan paket girmiş |
| Araç `ModuleNotFoundError: agents` | `bootstrap.sh` çalışmamış ya da yarıda kalmış; yeniden çalıştır |
| Akışta `{"error": …}` | Mesajı oku; `agentcore logs runtime --since 15m` |
