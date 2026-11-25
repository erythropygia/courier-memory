# Tasarım: Demo izi sayfası

- **Üretici:** `ui/demo/build.py`. Sekiz adımı `/flow/` ile aynı API çağrılarıyla, süreç içinde (`fastapi.testclient`, sunucu ve AWS yok) çalıştırır; başta ve sonda `POST /api/demo/reset`. Yanıtları görünüm modeline çevirir: `{day, courier, mode, built, steps[{agent, color, title, role, took[], trace[], source, gave{}}]}`.
- **Acil durum kapısı:** 2. halka Orkestratör izindeki `auto_decision` ya da `escalation` olayından kurulur; eşikler `agents.orchestrator.ESCALATE_*` sabitlerinden, "kaç günde müdür çağrıldı" değerlendirme günlerinin hepsinde `Orchestrator.plan` ile hesaplanır.
- **İz → görünüm:** `agents/trace.py` olaylarından `decision` düşünce, `tool` + eşleşen `result` tek araç satırı olur (`TOOL_TR` Türkçe ad). İz taşımayan yanıtlarda (`steps[]`: Brifing, Hafıza) araç satırları oradan gelir. Yaklaşma adımı kuraldır: üç konum satırı.
- **Sayfa:** `ui/demo/template.html` içindeki `/*__DATA__*/null` yerine JSON gömülür → `ui/demo/index.html` (~70 KB). Mobil öncelikli, tek sütun; üstte yapışkan ajan şeridi (görünen karta göre işaretlenir); araç ayrıntısı `<details>`.
- **QR:** `build.py --url <adres>` `segno` ile `ui/demo/qr.svg` ve `ui/story/data/demo-qr.svg` yazar. Hikaye Sahne 8'in son adımı (`last()`) QR'ı sağda gösterir; dosya yoksa pano boş kalır.
- **Yayın:** AWS'deki web uygulaması (ECS Fargate + ALB, `deploy/web`) sayfayı `api/main.py` üzerinden `/demo/` altında sunar; QR bu adrese gider (`build.py --url <WEB_URL>/demo/`). main'e push CI ile imajı yeniden dağıtır.

## Test

`api/tests/test_demo_page.py`: üretici sekiz halka döndürür, her halkada girdi, iz ve çıktı vardır; Hafıza çıktısında kapı şifresi yoktur; koşu canlı hafızayı değiştirmez.
