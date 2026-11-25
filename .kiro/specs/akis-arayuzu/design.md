# Tasarım: "Nasıl çalışır" arayüzü

- **Dosya:** `ui-flow/index.html` (HTML + CSS + JS tek dosya); `api/main.py` `/flow` altında sunar. Yazı tipleri `ui-story/fonts` klasöründen göreli yolla gelir.
- **Yerleşim:** üstte başlık, mod rozeti ve düğmeler; altında mimari şerit ve veri akışı satırı; üç sütun: adımlar · iz · sonuç + şube hafızası + ajan akışı.
- **Adım tanımı** (`STEPS`): başlık, ajan, kod ve API listesi, açıklama, vurgulanacak parçalar, veri akışı satırı ve `run()`. Yeni adım eklemek tek nesne eklemektir.
- **API tabanı:** `BASE`, sayfa yolundaki `/proxy/<port>` önekinden çıkarılır; yoksa kök. Bütün istekler `BASE + yol`.
- **İz:** `api()` her isteği ve yanıtı satır olarak yazar; `event()` `agents/trace.py` olaylarını çizer; iz taşımayan yanıtlarda (`steps[]`) araç ve sonuç satırları üretilir. Orkestratör arka planda başlatılır ve `?after=n` ile yoklanır.
- **Gerçek saha senaryosu:** not adımı kartsız bir durağa "park yeri yok… kapı şifresi…" notu bırakır; yaklaşma adımı aynı durağa 663 m, 221 m ve 0 m'den üç istek atar.
- **Müdür onayı** `decision: "approval"` gönderir (Orkestratör'ün kabul ettiği değer).

## Test

Uygulama içi tarayıcıda sekiz adım baştan sona, doğrudan ve test vekili arkasında (`/proxy/8000/flow/`). Otomatik arayüz testi yok.
