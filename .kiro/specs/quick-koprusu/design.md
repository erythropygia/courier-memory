# Tasarım: Amazon Quick köprüsü

## Genel bakış

```
Amazon Quick chat ajanı
   │  MCP connector (genel ağ, servisler arası OAuth)
   │  1. POST <Cognito>/oauth2/token  grant_type=client_credentials, scope=courier-memory/invoke
   │  2. tools/list · tools/call ask_courier_memory {question, day?}   Authorization: Bearer <jeton>
   ▼
AgentCore Gateway "courier-memory-quick"   MCP · CUSTOM_JWT (discoveryUrl, allowedClients=[quick])
   │  hedef "courier-memory": Lambda, araç şeması satır içi, kimlik GATEWAY_IAM_ROLE
   ▼
Lambda "courier-memory-quick-bridge"  (bridge_lambda.handler)
   │  araç adı ve soru denetimi · actorId = QUICK_ACTOR_ID (MUDUR-QUICK) · oturum quick-<uuid>
   │  InvokeAgentRuntime  SUPERVISOR_RUNTIME_ARN, okuma 270 sn, yeniden deneme yok
   ▼
Supervisor (agent) ──► planner · courier · memory_keeper · analyst
   ▲
   └── "data: {...}" akışı → parse_stream → {"answer"} ya da {"error"}
```

Köprü yeni bir ajan değildir: soru Supervisor'a olduğu gibi gider, cevap olduğu gibi döner. Hesap ve kimlik sınırı AgentCore tarafında kalır.

## Dosyalar

| Dosya | Ne |
|---|---|
| `deploy/quick/bridge_lambda.py` | `handler(event, context)`, `parse_stream`, `_tool_name`; ortam `SUPERVISOR_RUNTIME_ARN` (zorunlu), `QUICK_ACTOR_ID` |
| `deploy/quick/quick_bridge_setup.py` | `TOOL_SCHEMA`; `lambda_role`, `gateway_role`, `bridge_lambda`, `cognito`, `gateway`, `gateway_target`; `smoke_test` (`--test`) |
| `deploy/quick/README.md` | Kurulum, Quick tarafı, kimlik, sınırlar |
| `deploy/quick/tests/test_bridge_lambda.py` | AWS'ye gitmeyen testler (sahte istemci) |

## Kaynaklar

| Kaynak | Ad | Ayar | İzin |
|---|---|---|---|
| IAM rolü | `courier-memory-quick-lambda` | güven: `lambda.amazonaws.com` | `bedrock-agentcore:InvokeAgentRuntime` → Supervisor ARN ve `…/runtime-endpoint/*`; `AWSLambdaBasicExecutionRole` |
| Lambda | `courier-memory-quick-bridge` | Python 3.13, 280 sn, 256 MB | — |
| Cognito user pool | `courier-memory-quick` | alan adı `courier-memory-quick-<hesap>`; kaynak sunucusu `courier-memory`, kapsam `invoke` | — |
| Cognito istemcisi | `quick` | gizli anahtarlı, `client_credentials`, jeton 60 dk | — |
| IAM rolü | `courier-memory-quick-gateway` | güven: `bedrock-agentcore.amazonaws.com`, `aws:SourceAccount` = hesap | `lambda:InvokeFunction` → köprü Lambda'sı |
| AgentCore Gateway | `courier-memory-quick` | MCP, `CUSTOM_JWT` | — |
| Gateway hedefi | `courier-memory` | Lambda + satır içi araç şeması | Gateway rolü |

Kurulum sırası bağımlılığa göredir: Supervisor ARN → Lambda rolü → Lambda → Cognito → Gateway rolü (Lambda ARN'siyle) → Gateway (Cognito istemcisiyle) → hedef. Yeni rolün yayılması için Lambda oluşturma en çok on kez denenir; Gateway ve hedef `READY` olana dek beklenir.

## Lambda akışı

```
handler(event, context)
  araç adı = context.client_context.custom["bedrockAgentCoreToolName"] içinde "___" sonrası
     ≠ ask_courier_memory → {"error": "Bilinmeyen araç: …"}
  question boş → {"error": "Soru boş."} · > 2000 → {"error": "Soru en çok 2000 karakter olabilir."}
  payload = {"prompt": question, "actorId": QUICK_ACTOR_ID, "day"?: int(day)}
  InvokeAgentRuntime(SUPERVISOR_RUNTIME_ARN, runtimeSessionId="quick-<uuid>", accept=text/event-stream)
     akışta error → {"error": "Ajan yanıt veremedi: …"}
     AWS hatası  → log · {"error": "Courier Memory ajanına şu an ulaşılamıyor (<kod>)."}
  finally: akış kapatılır
  → {"answer": metin | "Ajan boş yanıt döndürdü."}
```

`parse_stream` Supervisor'ın yaptığıyla aynı biçimi okur (`agentcore-runtime` tasarımı, Uzman çağrısı): `messageStart` yeni mesaj açar, `contentBlockDelta.delta.text` parçaları birleşir, mesajlar satırla ayrılır.

## Kimlik ve gizli değerler

- `actorId` yalnız Lambda ortamından gelir. Quick'ten gelen olay yalnız `question` ve `day` taşır; başka alan okunmaz.
- `MUDUR-QUICK` müdür kimliğidir: bütün uzmanlar açıktır, kuryeye özel araçlar müdür adına çalışır. Kurye bazında yetki bu köprünün kapsamı dışındadır.
- Client Secret yalnız `~/.courier-memory/quick-bridge.json` dosyasındadır; konsola MCP adresi, Token URL ve Client ID yazılır. Dosya repoya konmaz, paylaşılmaz.

## Test

- `deploy/quick/tests/test_bridge_lambda.py` (4 test): soru sabit kimlikle ve yeni oturumla gider, olaydaki kimlik yok sayılır · bilinmeyen araç ve boş soru reddedilir · ajan hatası ve AWS hatası güvenli bildirilir · akıştan mesajlar birleşir.
- `quick_bridge_setup.py --test`: hesapta jeton → `tools/list` → bir `tools/call` ("Şube hafızasının özetini iki cümleyle ver.").

## Açık riskler

- Supervisor + uzman zinciri genelde 10–60 sn sürer; uzun plan istekleri Quick'in 300 sn sınırına yaklaşabilir. Lambda 280 sn, okuma 270 sn ile bunun altında kalır.
- Her soru yeni oturumdur: AgentCore Memory'deki konuşma olguları `MUDUR-QUICK` ad alanında birikir, oturum geçmişi taşınmaz.
- Cognito alan adı hesap kimliğini içerir (`courier-memory-quick-<hesap>`); Token URL paylaşılırken bu bilinmelidir.
- Kurulum ve uçtan uca deneme henüz dağıtım hesabında yapılmadı; Supervisor dağıtılmadan betik çalışmaz.
