# AgentCore Runtime dağıtımı

Courier Memory'nin Strands ajanını Amazon Bedrock AgentCore Runtime'a kurar. Spec: `.kiro/specs/agentcore-runtime/`. Kurallar: `.kiro/steering/agentcore.md`.

## Hızlı yol

Ön koşul: `agentcore` CLI, AWS kimliği (`aws sts get-caller-identity`) ve Bedrock'ta Anthropic model erişimi. AgentCore projesi reponun yanına kurulur (`../CourierMemory`); `CM_WORKSPACE` ile değiştirilebilir.

```bash
REPO=$(pwd)                                       # repo kökü
$REPO/deploy/agentcore/bootstrap.sh               # agentcore create + kod + veri + envVars
$REPO/deploy/agentcore/verify.sh                  # yerel ön kontrol
cd ../CourierMemory
agentcore dev --port 8081                         # ayrı terminal
agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünkü brifingim?","actorId":"O02"}'
agentcore deploy                                  # ilk dağıtım 5–8 dk
$REPO/deploy/agentcore/verify.sh CourierMemory --deployed    # Deploy · Tool · Observability
```

Kiro içinden aynı akış: sohbette `/deploy-courier-memory`, ya da `agentcore-runtime` spec'inde "9. görevden devam et".

## İstek

```json
{"prompt": "Rotamdaki park notlarını söyle.", "actorId": "O02", "day": 32}
```

| `actorId` | Rol | Açık araçlar |
|---|---|---|
| Kurye kimliği (`O02`, `K07`…) | kurye | Kendi `courier_id`'siyle: `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note` + herkese açık araçlar |
| `MUDUR-…` | müdür | Hepsi: ayrıca `plan_day`, `morning_review`, `region_report` |
| yok | konuk | `branch_memory_summary`, `real_day_evidence` |

Yanıt sunucu olayları olarak akar (`data: {"event": …}`); metin `contentBlockDelta.delta.text` parçalarındadır. Hata `data: {"error": …}` olarak gelir.

## Demo çağrıları

```bash
S=cm-demo-session-courier-o02-0000000001          # oturum kimliği en az 33 karakter
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"Bugünkü brifingimi ver.","actorId":"O02"}'
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"1. durağa not: sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakın. Kapı şifresi 2580. Konum 39.0120, 34.9783.","actorId":"O02"}'
agentcore invoke --runtime agent --session-id $S --payload '{"prompt":"K07 kuryesinin kartlarını göster.","actorId":"O02"}'      # reddedilir, konuşma sürer
agentcore invoke --runtime agent --payload '{"prompt":"Bugünün planını gerekçesiyle özetle.","actorId":"MUDUR-01"}'
agentcore invoke --runtime agent --payload '{"prompt":"Sistem dün neyi düzeltti?","actorId":"MUDUR-01"}'
agentcore traces runtime list --since 15m
```
Düz metin okumak için çıktıyı şuna bağlayın: `| sed -n 's/^data: //p' | jq -rj '.event.contentBlockDelta.delta.text // empty'; echo`

## Dosyalar

| Dosya | Ne |
|---|---|
| `runtime/main.py` | Giriş noktası |
| `runtime/cm/tools.py` | 9 Strands `@tool` (ince sarmalayıcı) |
| `runtime/cm/backend.py` | Araç takımı seçimi: `CM_TOOLSET=auto` (varsayılan) \| `full` \| `core` |
| `runtime/cm/core.py` | Çekirdek takım: alan kodu olmadan, yalnız `data/demo_run` ile 6 araç |
| `runtime/cm/scope.py` | Kimlik sınırı (`BeforeToolCallEvent`) |
| `runtime/cm/memory.py` | AgentCore Memory oturum yöneticisi |
| `runtime/cm/model.py` | Bedrock modeli (çıkarım profili kimliği) |
| `runtime/cm/prompt.py`, `payload.py` | İstem, istek gövdesi |
| `bootstrap.sh`, `verify.sh` | Kurulum · kontrol |
| `tests/test_runtime.py` | 21 test (iki araç takımı); Bedrock'a gitmez |

## Yerelde (AWS olmadan)

```bash
pip install -e ".[dev,agentcore]"
PYTHONUTF8=1 pytest -q deploy/agentcore/tests
```

## Durum

Kod ve betikler yerelde, gerçek `strands-agents` ve `bedrock-agentcore` paketleriyle ve sahte bir iskele üzerinde sınandı. `agentcore deploy` ve canlı Bedrock çağrısı henüz yapılmadı.
