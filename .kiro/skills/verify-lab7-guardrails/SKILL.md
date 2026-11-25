---
name: verify-lab7-guardrails
description: Dağıtılmış Courier Memory ajanının Lab 7 şartlarını (Deploy, Observability, Tool) ve kayıt şartını (spec klasörü) denetler, eksikleri nedenleriyle raporlar. "Lab 7 kontrolü", "guardrail kontrolü", "hazır mıyız" istendiğinde kullan.
---

# Lab 7 kontrolü

Kod değiştirme; yalnız denetle ve raporla. Bir kontrol başarısızsa nedenini bul, düzeltmeyi öner, onay almadan uygulama.

## Adımlar

1. Yerel ve dağıtılmış kontroller:
   ```bash
   $REPO/deploy/agentcore/verify.sh CourierMemory --deployed
   ```
2. Kayıt şartı: `~/environment/.kiro/specs/agentcore-runtime/` içinde `requirements.md`, `design.md`, `tasks.md` var mı; `tasks.md` içinde 9–13. görevler işaretli mi.
3. İz içeriği (araç adımı görünüyor mu):
   ```bash
   cd ~/environment/CourierMemory
   agentcore traces runtime list --since 15m
   agentcore traces runtime get <trace-id>      # indirilen JSON'da araç adını ve süresini bul
   ```
4. Kimlik sınırı: `deploy-courier-memory` skill'inin 7. adımındaki üç çağrı.

## Rapor biçimi

| Şart | Durum | Kanıt |
|---|---|---|
| Deploy | ✓ / ✗ | `agentcore status` çıktısındaki ARN |
| Observability | ✓ / ✗ | `envVars` girdisi + log grubu adı + iz kimliği |
| Tool | ✓ / ✗ | Akışta çağrılan araç adı ve döndürdüğü verinin bir satırı |
| Kayıt | ✓ / ✗ | Spec klasörü ve işaretli görevler |

Ardından esnetme hedeflerinin durumunu tek satırla ekle: hafıza (AgentCore Memory), kimlik sınırı, Gateway, sohbet arayüzü.
