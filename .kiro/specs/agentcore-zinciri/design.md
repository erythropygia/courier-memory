# Tasarım: AgentCore zinciri

- **Yayın (`api/live.py`):** `Live.start(target, kind)` koşunun türünü (`day | agentcore`) tutar; `Live.runner(make_chain)` başka bir zinciri aynı `_work` ile koşturur (zincir `"error"` döndürebilir). `snapshot` ve SSE `hello` `kind` taşır; `hello.ctx.agentcore` zincirin açık olduğunu söyler. Tek koşu kuralı iki zincir için ortaktır (409).
- **İstemci (`api/agentcore_client.py`):** `SupervisorClient` ARN'yi `ListAgentRuntimes` ile adla bulur (sayfalı, önbellekli; ölümcül hatada unutur), `InvokeAgentRuntime` akışını `data:` satırlarından JSON olarak verir. botocore: `read_timeout=120`, `total_max_attempts=1`. `friendly()` istisnayı gösterilebilir `AgentCoreError`'a çevirir (`fatal`: kimlik, izin, runtime yok, bağlantı); ayrıntı yalnız sunucu günlüğüne. `scrub()` ARN ve 12 haneli hesap numarasını metinden çıkarır.
- **Zincir (`api/agentcore_chain.py`):** `STEPS` altı `Step(actor, prompt, agent, tool, expect)`. Adım: `step` → `http` (InvokeAgentRuntime, gövde) → `StreamReader` (`cm_trace` → `map_trace` → `ev` hemen; metin toplanır; `toolUse` yedek izi adım sonunda yalnız `cm_trace` gelmediyse) → `http_done` → `ev answer` → `result {path, tools, denied, traced, ...}`. Ölümcül hata zinciri durdurur, diğerleri yalnız adımı düşürür.
- **Uçlar (`api/main.py`):** `POST /api/live/start?chain=day|agentcore` (`CM_AGENTCORE_CHAIN=0` → 501).
- **Arayüz (`ui/flow/index.html`):** sunum ekranında ikinci düğme; `run.kind` adım tanımlarını (`AC_STEPS`) ve mimari şeridi (Kullanıcı · Supervisor · uzmanlar · alan ajanları · DynamoDB · Athena) seçer. `acEvent` ajan rozeti, `parent` için girinti, `denied` için çizgili kırmızı satır çizer; canlı atlama şeritte yanar. Telefon düzeni değişmez.
- **Dağıtım (`deploy/web/ecs_deploy.py`):** satır içi politika `agentcore-supervisor`; ortam `CM_AGENTCORE_CHAIN=1`, `CM_AGENTCORE_SUPERVISOR`.

## Test

`api/tests/test_agentcore_chain.py` (sahte boto3, AWS'ye gidilmez): altı adım sırayla, kimlikler, iç içe atlama ve ret, `cm_trace` varken yedek iz yok; oturum ≥ 33 ve kimlik başına sabit, ARN bir kez aranır; `cm_trace`'siz yedek; ölümcül hatalar tek başarısız adım ve AWS ayrıntısı yok; akış hatası ve zaman aşımı yalnız adımını düşürür; koşu sürerken 409; kapalıyken 501; görev rolü politikası.
