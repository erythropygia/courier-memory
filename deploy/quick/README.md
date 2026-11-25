# Amazon Quick köprüsü

Amazon Quick'teki bir chat ajanından Courier Memory'ye canlı soru sormak için MCP köprüsü.

```
Quick chat ajanı ──(MCP, OAuth client credentials)──► AgentCore Gateway ──► Lambda (bridge_lambda.py)
                                                                              └─► supervisor runtime (agent) ──► uzman ajanlar
```

## Kurulum

Önce AgentCore projesi dağıtılmış olmalı (`deploy/agentcore/README.md`; supervisor runtime adı `CourierMemory_default_agent`).

```bash
AWS_PROFILE=<profil> AWS_REGION=us-east-1 python deploy/quick/quick_bridge_setup.py --test
```

Betik tekrar çalıştırılabilir. Kurduğu kaynaklar:

| Kaynak | Ad | İzin |
|---|---|---|
| IAM rolü | `courier-memory-quick-lambda` | yalnız supervisor runtime'ını çağırır |
| Lambda | `courier-memory-quick-bridge` | `bridge_lambda.handler`, 280 sn |
| Cognito user pool | `courier-memory-quick` | makineler arası anahtar (`client_credentials`, kapsam `courier-memory/invoke`) |
| IAM rolü | `courier-memory-quick-gateway` | yalnız bu Lambda'yı çağırır |
| AgentCore Gateway | `courier-memory-quick` | MCP, `CUSTOM_JWT` (yalnız bu Cognito istemcisi); araç `ask_courier_memory` |

Quick'e girilecek değerler `~/.courier-memory/quick-bridge.json` dosyasına yazılır. Dosya Client Secret içerir; repoya koymayın, paylaşmayın.

## Quick tarafı

1. **Connectors → Create → Cloud connector → Model Context Protocol**.
2. MCP server endpoint: dosyadaki `mcp_url`; connection type: Public network.
3. Auth configuration: **Service-to-service OAuth**; Client ID, Client secret, Token URL dosyadan.
4. Bir chat ajanı oluşturup bu connector'ı **Actions** olarak bağlayın.

Quick'in açıklama alanı yalnız harf, rakam, boşluk ve `. , ! ? - _` kabul eder (Türkçe karakter yok).

## Kimlik

Quick'ten gelen her soru `QUICK_ACTOR_ID` (varsayılan `MUDUR-QUICK`, müdür) kimliğiyle gider. Kimlik Lambda ortamından
gelir; Quick ya da model değiştiremez. Kurye bazında yetki gerekiyorsa Quick'te kullanıcı girişli OAuth ve Lambda'da
token'dan kimlik eşlemesi gerekir.

## Sınırlar

Quick her MCP çağrısında 300 sn bekler; supervisor + uzman genelde 10–60 sn sürer. Her soru yeni bir oturumdur
(konuşma bağlamını Quick'in kendi sohbeti taşır).
