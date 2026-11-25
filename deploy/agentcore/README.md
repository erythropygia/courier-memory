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

## Çok ajanlı yapı (varsayılan)

`bootstrap.sh` aynı kod paketinden beş AgentCore runtime'ı tanımlar; rolü `CM_AGENT_ROLE` seçer (`runtime/cm/roles.py`):

```
agent (Supervisor)      kullanıcı buna konuşur; işi uzmana yönlendirir, cevabı birleştirir
 ├─ planner             Planlama Ajanı → plan_day, morning_review, region_report        (müdür)
 ├─ courier             Kurye Ajanı    → courier_briefing, stop_cards, approaching_stop
 ├─ memory_keeper       Hafıza Ajanı   → leave_note, branch_memory_summary, real_day_evidence,
 │                                       harvest_questions (Hasat Ajanı; müdür)
 └─ analyst             Analiz Ajanı   → query_history: Athena'da salt okunur SQL      (müdür)
```

Uzmanların araçları repodaki ajanları çağırır: `plan_day` → Orkestratör + Atama, `morning_review` → Değerlendirme,
`region_report` → Bölge, `courier_briefing` → Brifing, `leave_note` → Hafıza, `harvest_questions` → Hasat.
Bu iç ajanlar AgentCore'da kurallı yoldan çalışır (`CM_LLM_MODE=mock`); modele yalnız runtime ajanları gider.

**Analiz Ajanı için önce Athena:** `AWS_PROFILE=… AWS_REGION=us-east-1 python deploy/athena/athena_setup.py`
(bucket, çalışma grubu, `courier_memory` veritabanı ve dört tablo; ayrıntı: dosyanın başı). Ajan yalnız tek bir `SELECT`
çalıştırabilir (en çok 200 satır, sorgu başına 100 MB tarama); rolü yalnız okuma ve sonuç klasörüne yazma iznine sahiptir
(`agentcore/analyst-policy.json`). Kurye notları ve kurye adları Athena'ya yüklenmez.

- Supervisor uzmanı `InvokeAgentRuntime` ile çağırır (`runtime/cm/delegate.py`); ARN'yi adla bulur, tek `agentcore deploy` yeter.
  İzin yalnız bu projenin runtime'larıdır: `agentcore/supervisor-policy.json` (`agentcore_config.py` yazar).
- Kimlik modelden gelmez: uzmana isteğin `actorId`'si gider ve uzman kimlik sınırını (`cm/scope.py`) kendisi uygular.
- `agentMemory` her runtime'a bağlanır; her uzman kendi oturumunu tutar (`<oturum>-<rol>`).
- Uzmanı doğrudan çağırmak: `agentcore invoke --runtime planner --payload '{"prompt":"Bugünün planı?","actorId":"MUDUR-01"}'`.
- Tek runtime (dokuz araç, eski yapı): `CM_MULTI_AGENT=0 deploy/agentcore/bootstrap.sh`, sonra `agentcore deploy`.
- Bedeli: supervisor üzerinden her istek en az iki model çağrısıdır (supervisor + uzman); yanıt biraz daha geç gelir.

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

## Canlı zincir izi (`cm_trace`)

Akışta model olaylarının arasında `data: {"cm_trace": {…}}` satırları da gelir: her runtime kendi araç adımlarını,
supervisor ayrıca uzmandan gelen adımları yazar. Yalnız `event`/`error` okuyan tüketiciler (verify.sh, köprü Lambda,
`delegate.parse_stream`) bu satırları yok sayar; cevap metni değişmez. Kod: `runtime/cm/trace.py`, test: `tests/test_trace.py`.

| Alan | Anlamı |
|---|---|
| `seq` | İstek içinde artan sıra (aktarılan uzman adımları supervisor sırasına yeniden numaralanır) |
| `agent` | `supervisor` · `planner` · `courier` · `memory_keeper` · `analyst` · `all` |
| `parent` | `null`; uzmandan aktarılan ve delegasyon olaylarında `"supervisor"` |
| `type` | `tool_call` · `tool_result` · `delegate_start` · `delegate_end` · `denied` · `error` |
| `tool` / `input` | Araç adı ve girdisi (yoksa `null`); telefon, hitaplı ad, şifre/kod rakamları maskelenir |
| `summary` | Kısa Türkçe özet (en çok 400 karakter); `tool_result`'ta JSON sonucun alan/sayı özeti |
| `ms` / `ok` | Süre ve başarı; yalnız `tool_result` ve `delegate_end`'de, diğerlerinde `null` |

Sıra kuralları:
- Her araç: `tool_call` → `tool_result`. Kimlik sınırı (`cm/scope.py`) reddederse yalnız `denied` (gerekçe `summary`'de), sonuç satırı yok.
- Supervisor `ask_*`: `tool_call(ask_…)` → `delegate_start` (girdi `{"question","day"}`) → uzmanın iz satırları (`parent:"supervisor"`)
  → `delegate_end` (cevabın ilk ~300 karakteri) → `tool_result(ask_…)`. Uzman hatasında `error` + `delegate_end(ok:false)`, ardından araç hatası.
- İz kuyruğu isteğe aittir (Strands `invocation_state`); araç sürerken (uzman çağrısı) 100 ms'de bir boşaltılır, sunum ekranı zinciri canlı görür.

```
data: {"cm_trace": {"seq": 1, "agent": "supervisor", "parent": null, "type": "tool_call", "tool": "ask_planner", "input": {"question": "Bugünün planı?", "day": 32}, "summary": "ask_planner çağrılıyor", "ms": null, "ok": null}}
data: {"cm_trace": {"seq": 2, "agent": "planner", "parent": "supervisor", "type": "delegate_start", "tool": null, "input": {"question": "Bugünün planı?", "day": 32}, "summary": "Planlama Ajanına soruluyor: Bugünün planı?", "ms": null, "ok": null}}
data: {"cm_trace": {"seq": 3, "agent": "planner", "parent": "supervisor", "type": "tool_call", "tool": "plan_day", "input": {"day": 32}, "summary": "plan_day çağrılıyor", "ms": null, "ok": null}}
data: {"cm_trace": {"seq": 4, "agent": "planner", "parent": "supervisor", "type": "tool_result", "tool": "plan_day", "input": null, "summary": "day=32, assignments: 9 öğe", "ms": 41, "ok": true}}
data: {"cm_trace": {"seq": 5, "agent": "planner", "parent": "supervisor", "type": "delegate_end", "tool": null, "input": null, "summary": "Plan hazır: 9 kurye.", "ms": 2310, "ok": true}}
data: {"cm_trace": {"seq": 6, "agent": "supervisor", "parent": null, "type": "tool_result", "tool": "ask_planner", "input": null, "summary": "Plan hazır: 9 kurye.", "ms": 2315, "ok": true}}
```

İzleri canlı okumak: `| sed -n 's/^data: //p' | jq -c 'select(.cm_trace) | .cm_trace | [.seq, .agent, .type, .tool, .summary]'`

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
| `runtime/cm/trace.py` | Canlı zincir izi (`cm_trace`): araç kancası, istek başına iz kuyruğu, uzman izini aktarma |
| `runtime/cm/memory.py` | AgentCore Memory oturum yöneticisi |
| `runtime/cm/model.py` | Bedrock modeli (çıkarım profili kimliği) |
| `runtime/cm/prompt.py`, `payload.py` | İstem, istek gövdesi |
| `bootstrap.sh`, `verify.sh` | Kurulum · kontrol |
| `tests/test_runtime.py` | 21 test (iki araç takımı); Bedrock'a gitmez |
| `tests/test_trace.py` | `cm_trace` sırası, ret, supervisor aktarımı, hata; Bedrock'a gitmez |

## Yerelde (AWS olmadan)

```bash
pip install -e ".[dev,agentcore]"
PYTHONUTF8=1 pytest -q deploy/agentcore/tests
```

## Durum

Kod ve betikler yerelde, gerçek `strands-agents` ve `bedrock-agentcore` paketleriyle ve sahte bir iskele üzerinde sınanır.
Dağıtım `us-east-1`'de yapıldı: beş runtime ve `agentMemory` çalışıyor, `verify.sh CourierMemory --deployed` üç kontrolü geçiyor,
Supervisor üzerinden planner, courier ve analyst canlı yanıt veriyor. `main`'e push'ta CI (`.github/workflows/ci-cd.yml`) yeniden dağıtır.
