---
name: verify-deployment
description: Dağıtılmış Courier Memory ajanının üç dağıtım şartını (Deploy, Observability, Tool) ve kayıt şartını (spec klasörü) denetler, eksikleri nedenleriyle raporlar. "Dağıtım kontrolü", "guardrail kontrolü", "hazır mıyız" istendiğinde kullan.
---

# Dağıtım kontrolü

Kod değiştirme; yalnız denetle ve raporla. Bir kontrol başarısızsa nedenini bul, düzeltmeyi öner, onay almadan uygulama.

`REPO` = bu reponun kökü. AgentCore projesi `$CM_WORKSPACE/CourierMemory` (varsayılan: `../CourierMemory`).

## Adımlar

1. Yerel ve dağıtılmış kontroller:
   ```bash
   $REPO/deploy/agentcore/verify.sh CourierMemory --deployed
   ```
2. Kayıt şartı: `.kiro/specs/agentcore-runtime/` içinde `requirements.md`, `design.md`, `tasks.md` var mı; `tasks.md` içinde 9–13. görevler işaretli mi.
3. İz içeriği (araç adımı görünüyor mu):
   ```bash
   cd ../CourierMemory
   agentcore traces runtime list --since 15m
   agentcore traces runtime get <trace-id>      # indirilen JSON'da araç adını ve süresini bul
   ```
4. Kimlik sınırı: `deploy-courier-memory` skill'inin 7. adımındaki üç çağrı.
5. Çok ajanlı yapı: `agentcore status` beş runtime'ı (`agent`, `planner`, `courier`, `memory_keeper`, `analyst`) dağıtılmış göstermeli; `deploy-courier-memory` skill'inin 8. adımındaki çağrılarda araç adları doğru uzmanı göstermeli (`ask_planner`, `ask_courier_agent`, `ask_analyst`), O02'nin plan isteği uzman çağrılmadan reddedilmeli.

## Rapor biçimi

| Şart | Durum | Kanıt |
|---|---|---|
| Deploy | ✓ / ✗ | `agentcore status` çıktısındaki ARN |
| Observability | ✓ / ✗ | `envVars` girdisi + log grubu adı + iz kimliği |
| Tool | ✓ / ✗ | Akışta çağrılan araç adı ve döndürdüğü verinin bir satırı |
| Kayıt | ✓ / ✗ | Spec klasörü ve işaretli görevler |
| Çok ajanlı | ✓ / ✗ | Beş runtime ARN'i + her uzmana giden bir çağrının araç adı |

Ardından sonraki adımların durumunu tek satırla ekle: hafıza (AgentCore Memory), kimlik sınırı, Athena (`athena-analiz`), Quick köprüsü (`quick-koprusu`), web ve CI/CD ile kalıcı depo (`aws-dagitim`).
