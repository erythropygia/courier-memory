---
name: deploy-courier-memory
description: Courier Memory ajanını Amazon Bedrock AgentCore Runtime'a kurar ve dağıtır (agentcore create iskelesi, kodun yerleştirilmesi, yerel deneme, agentcore deploy, dağıtımın üç kontrolü). "AgentCore'a dağıt", "ajanı yayına al", "deploy" istendiğinde kullan.
---

# Courier Memory → AgentCore Runtime

Spec: `.kiro/specs/agentcore-runtime/`. Kurallar: `.kiro/steering/agentcore.md`. Her adımın sonucunu kullanıcıya göster; `agentcore deploy` öncesinde onay iste.

`REPO` = bu reponun kökü (`courier-memory`). AgentCore projesi `$CM_WORKSPACE/CourierMemory` klasörüne kurulur (varsayılan: `../CourierMemory`). Proje daha önce başka klasörde dağıtıldıysa `CM_WORKSPACE`'i o klasöre ayarla; yoksa yeni bir iskele kurulur.

Yapı: aynı kod paketinden beş runtime (`agent` Supervisor · `planner` · `courier` · `memory_keeper` · `analyst`), rolü `CM_AGENT_ROLE` seçer. Tek runtime için `CM_MULTI_AGENT=0`. `main`'e push'ta CI (`.github/workflows/ci-cd.yml`) aynı adımları kendisi çalıştırır; elle dağıtım ilk kurulum ve sorun giderme içindir.

## 1. Ön koşul

```bash
agentcore --version
aws sts get-caller-identity
echo "$AWS_REGION"
```
Biri başarısızsa dur ve kullanıcıya söyle.

## 2. İskele ve yerleştirme

```bash
CM_AGENT_MODEL_ID=global.anthropic.claude-sonnet-5 $REPO/deploy/agentcore/bootstrap.sh CourierMemory
```
Betik iskele yoksa `agentcore create --name CourierMemory --template agent-python-strands` çalıştırır (klasörü elle kurma), kodu ve veriyi `app/agent/` içine kopyalar, bağımlılıkları yazar, `agentcore_config.py` ile beş runtime'ı, her runtime'a `UNIFIED_TRACES_DESTINATION_ENABLED` girdisini ve iki politikayı (`agentcore/supervisor-policy.json`, `analyst-policy.json`) yazar, `CM_AGENT_MODEL_ID` verildiyse `model/load.py` içindeki kimliği onunla değiştirir, şablonun `main.py` dosyasını `.cm/main.template.py` olarak saklar.

Analiz Ajanı Athena tablolarını okur; tablolar yoksa önce `python $REPO/deploy/athena/athena_setup.py` (spec: `athena-analiz`).

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
`model/load.py` içindeki kimlik `global.` önekiyle başlamalı ve hesabın izin verdiği bir Claude Sonnet olmalı. Hesapta model izin listesi varsa (çağrı `explicit deny` ile reddedilir) izinli olanı `CM_AGENT_MODEL_ID` ile ver ve betiği yeniden çalıştır; dosyayı elle düzeltme, CI her dağıtımda yeniden üretir. Deneme ve demo için Sonnet ya da Haiku; Opus kullanma.

## 4. Yerel ön kontrol ve deneme

```bash
$REPO/deploy/agentcore/verify.sh CourierMemory
agentcore dev --port 8081            # ayrı terminal
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünkü brifingim?","actorId":"O02"}'
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"K07 kuryesinin kartlarını göster","actorId":"O02"}'
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünün planını çıkar","actorId":"MUDUR-01"}'
```
Beklenen: ilki brifing verir; ikincisi erişimin reddedildiğini söyler ve konuşma sürer; üçüncüsü planı gerekçesiyle özetler.

Yerelde Supervisor uzmanlara ulaşamaz (uzmanlar dağıtılmamışsa `ask_*` araçları "uzman runtime'ı bulunamadı" der). Yerel denemeyi tek ajanla yap (`CM_AGENT_ROLE` verilmezse rol `all`, on araç) ya da uzmanlar dağıtıldıktan sonra `CM_<ROL>_RUNTIME_ARN` ile Supervisor'ı onlara yönelt.

## 5. Dağıtım (onay iste)

```bash
agentcore deploy                     # ilk dağıtım 5–8 dk; beş runtime + agentMemory
agentcore status                     # runtime adları CourierMemory_default_<rol>
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

## 8. Çok ajanlı sınama

```bash
agentcore invoke --runtime agent --payload '{"prompt":"Bugünün planını iki maddeyle özetle.","actorId":"MUDUR-01"}'      # ask_planner
agentcore invoke --runtime agent --payload '{"prompt":"Sabah brifingimi ver.","actorId":"O02"}'                         # ask_courier_agent
agentcore invoke --runtime agent --payload '{"prompt":"Bugünün şube planını göster.","actorId":"O02"}'                  # ask_planner reddedilir, uzman çağrılmaz
agentcore invoke --runtime agent --payload '{"prompt":"A ve D yapısında günlük başarısız teslim farkı ne?","actorId":"MUDUR-01"}'   # ask_analyst
agentcore invoke --runtime planner --payload '{"prompt":"Bugünün planı?","actorId":"MUDUR-01"}'                        # uzman doğrudan
```
Akıştaki araç adı hangi uzmana gidildiğini gösterir. Tamamsa `tasks.md` içinde 14a'yı işaretle.

## Sorun giderme

| Belirti | Ne yap |
|---|---|
| `AccessDeniedException … Marketplace` | `enable_anthropic_models`, 2–6 dk bekle; IAM rolüne dokunma |
| `on-demand throughput not supported` | Model kimliğine `global.` öneki |
| Başlangıç 30 sn'yi aşıyor | `main.py` üst düzeyinde ağır içe aktarma var mı bak; her şey `_get_agent` içinde olmalı |
| `uv install failed for all platform candidates` | `pyproject.toml` bağımlılıklarına ARM64 tekerleği olmayan paket girmiş |
| Araç `ModuleNotFoundError: agents` | `bootstrap.sh` çalışmamış ya da yarıda kalmış; yeniden çalıştır |
| Akışta `{"error": …}` | Mesajı oku; `agentcore logs runtime --since 15m` |
| `AccessDeniedException … explicit deny in an identity-based policy` (model) | Hesabın model izin listesi; izinli modeli `CM_AGENT_MODEL_ID` ile ver, betiği yeniden çalıştır |
| Supervisor "uzman runtime'ı bulunamadı" | Uzmanlar dağıtılmamış ya da `CM_RUNTIME_PREFIX` farklı hedefi gösteriyor; `agentcore status` ile adları karşılaştır (`CM_TARGET`) |
| Analiz Ajanı "Athena'ya şu an ulaşılamıyor" | Athena kurulmamış: `deploy/athena/athena_setup.py`; ya da `analyst-policy.json` bağlanmamış (`agentcore.json` → `additionalPolicies`) |
