# Gereksinimler: Sabah akışı (şubeden çıkış)

## Giriş

Mesai 09:00'da başlar ama kurye bugün ~10:30'da çıkar: araçtan indirme (okutmalı), kuryenin kendi gönderilerini ayrıştırması, zimmet ve yükleme. Gönderiler ve kurye ataması araç gelmeden bellidir, rotalama 09:00'da hazırdır. Ayrıştırma indirme okutmasına gömülürse ("kurye · raf · yükleme sırası") kurye yalnız rafını zimmetleyip yükler; çıkış en geç ~09:30 olur. Süreler şube sahibinin saha bilgisidir (VARSAYIM); büyüklüğü pilot ölçer. Dinamik planlamada bu bir zorunluluktur: bölgeler her sabah değiştiği için kurye "kendi alanının" gönderilerini ezbere ayıramaz.

## Gereksinim 1: Simülatörde sabah modeli
1. `morning` config bölümü: `enabled`, `current_min` (90), `presorted_min` (30), `deviation_min` (10), `presorted_arms` ([D]). Kapalıyken çıkış = mesai başı ve sonuçlar Faz 0–4 ile birebir aynıdır.
2. Çıkış = `planning.start_minute` + kolun sabah süresi + kurye sapması (normal σ, ±2σ kesik). Sapma ayrı bir RNG akışından (`S_MORNING`) gelir, aynı gün aynı kurye için kollar arası aynıdır (CRN); diğer akışları değiştirmez. Isınma bugünkü süreçtir.
3. Rota çıkış saatinden yürür (varışlar, öğle penceresi ve saate bağlı "alıcı yok" bu saate göre). Rota süresi ve vardiya bandı ölçüleri (planlanan/gerçekleşen) rota süresidir; değişmez.
4. **Fazla mesai vardiya bitişinden (saat) sayılır:** mesai başı + bant üstü (09:00 + 528 = 17:48). Geç çıkış da fazla mesai yaratır. Faz 2c kısıtının vardiya bitişi aynı saattir (`RepairLimits.shift_end_at`), çıkış kayınca kaymaz.
5. Kol D'nin planı beklenen çıkıştan (sapmasız) başlar; ajan aynı değeri kullanır (408/408 birebir korunur).
6. Kol D karşı-olgusu `current_morning`: aynı plan, ipuçları ve rastgele sayılar; yalnız çıkış bugünkü sabahla. `summary.morning` kol başına çıkış/dönüş ortalamasını ve karşı-olgunun günlük farkını (fazla mesai, başarısız, alıcı yok, dönüş, vardiya sonrası dönen pay) taşır.
7. Hafızanın katkısını ölçen deneyler (tarama, öğrenme, ablasyonun hafıza varyantları) sabahı tüm kollarda eşit tutar (`morning.presorted_arms=[]`); ablasyonda `full_morning` varyantı ve `morning` çifti sabah katkısını ayrıca ölçer.
8. Testler: `sim/tests/test_morning.py` (5 hızlı).

## Gereksinim 2: Ajan
1. `agents/route.py`: `morning_info(cfg)`, `plan_departure(sb, arm)`; `RoutePlanner` planı ve tahmini dönüşü çıkış saatinden hesaplar; vardiya bitişi saat olarak sabit.
2. Orkestratör aracı `sorting_plan {}` (atama ve rota kontrollerinden sonra, öneriden önce): her kurye bir raf; gönderi, durak, ilk ve son yüklenen (yükleme sırası rota tersi), ertesi gün rafı (bugün kapalı bilinen duraklar), tahmini çıkış (bugünkü süreç ↔ ayrıştırmasız). Deterministik; paket başına LLM çağrısı yok. Kurallı yedek aynı sırayla çağırır, gerekçeye bir cümle ekler; öneri `morning` özeti taşır.
3. Brifing başlangıç ve dönüş saatini rotadan alır.
4. Testler: `agents/tests/test_phase5.py` (3 hızlı).

## Gereksinim 3: API ve arayüz
1. `GET /api/morning/{gün}`: ayrıştırma planı (onaylı plan varsa onunla), kol D'nin rota başına çıkışı ↔ aynı rota bugünkü sabahla, `summary.morning`, uygulamanın ürettiği örnek gönderi kimlikleri (`G<gün>-<adres>-<sıra>`; barkod değil).
2. `POST /api/morning/scan {day, shipment}`: raf, kurye, durak ve yükleme sırası; bugün kapalı bilinen adres → ertesi gün rafı; planda yok → "esnek" raf (istisna, müdür ekranına).
3. Hikaye: Sahne 3'ün onaydan sonraki adımı "İndirme okutması → raf" (raf ızgarası, okutma akışı, ortalama çıkış ölçümü); Sahne 2 izinde `sorting_plan` vuruşu; Sahne 7 şelalesinde "Sabah" kalemi. API yoksa kayıtlı yanıtlar (`tools/record_fallback.py`).
4. Testler: `api/tests/test_phase5_api.py` (1 hızlı).

## Gereksinim 4: Ekonomi ve dürüstlük
1. Şelale: "Hafıza + Brifing" kalemi kol D'nin bugünkü sabahla hâlidir (karşı-olgu); "Sabah" kalemi ayrıdır. Hafızanın getirisi (`gain.vs_C`) yalnız hafızayı ölçer; `morning` bölümü (içinde `morning.gain`) sabah kalemini verir; `gain` yalnız `vs_C`, `vs_B` tutar.
2. Erken çıkışın vardiya içinde açtığı kapasite (daha az kurye ihtiyacı) para değerine çevrilmez; bu açıkça yazılır.
3. Sunumda sabah süreleri "saha bilgisi, VARSAYIM; pilot ölçer" diye anılır; ajanın rolü dürüstçe anlatılır: paket başına talimat plandan çıkan tablodur, ajan istisnaları yönetir.
