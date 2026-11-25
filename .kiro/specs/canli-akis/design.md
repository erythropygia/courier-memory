# Tasarım: Canlı akış

- **Sunucu (`api/live.py`):** `Live` tek koşuyu ve olay listesini bellekte tutar (web tek ECS görevi, tek süreç). `start()` koşu sürerken `LiveBusy` (409) atar, yoksa koşu numarasını artırıp listeyi boşaltır ve `Chain`'i arka plan iş parçacığında çalıştırır. `Chain` adımları `/flow/`'un eski adımlarıyla ve `ui/demo/build.py` ile aynı uç fonksiyonlarını aynı gövdelerle süreç içinde çağırır; çağrı izde `http` + `http_done` olarak görünür. Orkestratör izi oturumdan canlı okunur; izini sonunda döndüren ajanlarda olaylar 0,1 sn arayla yayınlanır, adımlar arası 1,4 sn.
- **Yayın (`GET /api/live/stream`):** async üreteç (izleyici başına iş parçacığı yok), 0,25 sn'de bir `pull(run, n)`. Koşu değiştiyse yeni koşunun hepsi gönderilir (ilk olay `run`: istemci sıfırlar). `id: <run>:<n>` → tarayıcı yeniden bağlanınca Last-Event-ID ile sürer. 15 sn'de bir yorum satırı CloudFront (60 sn) ve ALB (300 sn) zaman aşımlarını aşar.
- **Arayüz (`ui/flow/index.html`):** olay güdümlü. Adım başına olaylar saklanır; izleyici biten adıma dönebilir. Ayrıntı JSON'u yalnız açılınca yazılır. `?sunum=1` "Günü planla"yı gösterir; iframe içindeyse tuşları `postMessage` ile hikayeye iletir, değilse QR'ı kendisi çizer. ≤ 760 px tek sütun.
- **Hikaye:** Sahne 2 harita + "Günü planla" (`CM.liveStart`), Sahne 3 iframe (`&start=1&qr=1`). `js/qr.js` QR'ı `vendor/qrcode.js` (MIT) ile `CM.flowUrl()`'den üretir; `main.js` sahneye göre gösterir, Q açar/kapatır, iframe'den gelen tuşları işler.
- **HTTPS:** `/story`, `/flow`, `/demo` için parametresiz göreli `307` rotaları (Starlette'in mutlak yönlendirmesi yerine).

## Test

`api/tests/test_live.py`: koşu bir kez çalışır ve ikinci başlatma 409; sekiz `step` ve `result`, hata yok, kapı temassız; olaylar sıralı; ipucunda şifre yok; yeni koşuda izleyici baştan alır; yönlendirme göreli ve sorgudan hedef almaz.
