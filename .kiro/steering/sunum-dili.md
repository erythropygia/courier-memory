---
inclusion: always
---
# Sunum ve arayüz dili

Bu kurallar kullanıcıya görünen her metin için geçerlidir: arayüz, ajan yanıtları, sunum.

## Sözlük

| Terim | Anlamı |
|---|---|
| **Mevcut yapı** | Sabit kurye bölgeleri. Kurye her gün aynı bölgeye gider. |
| **Yeni yapı** | Dinamik planlama. Bölgeler her sabah günün gönderilerine göre yeniden çizilir, rota çıkarılır. |
| **Durak** | Farklı bir teslim noktası. Bir durakta birden fazla gönderi olabilir. |
| **Blok** | ~300 m'lik alan. "Kurye bu sokağı tanıyor mu" sorusu blok düzeyinde sorulur. |
| **Kurye–bölge uyumu** | Kuryenin bir bloktaki geçmiş başarısı ve tanıdıklığı, bloğun genel ortalamasına göre. |
| **Hafıza kapsamı** | Rotadaki durakların ne kadarında geçerli en az bir not olduğu. |
| **Vardiya bandı** | 378–528 dk (7–8 saat, ±%10). |

## Kurallar

1. Şirket içi sistem adları (mevcut çizelgeleme sisteminin ve dinamik planlama motorunun iç adları) hiçbir çıktıda geçmez. "Mevcut yapı", "yeni yapı", "dinamik planlama" denir.
2. Şirketi temsil ediyoruz: **Mevcut yapı kötülenmez.** Dil nötr kalır. Mevcut yapının güçlü yanı (kuryenin bölgesini tanıması) da gösterilir; zaten bu projenin çıkış noktası budur.
3. Vurgular, bu sırayla:
   - ilk denemede teslim
   - dengeli iş yükü
   - kurye sayısı ve yol tasarrufu
4. "Performans puanı" yerine **"kurye–bölge uyumu"** denir. Kurye sıralaması gösterilmez.
5. Kurye ekranında ve ipuçlarında tek cümle kuralı geçerlidir. Sürüş sırasında ekrana bakma gerektiren hiçbir şey yoktur.
6. Sayfalar veri odaklı ve az yazılı olur. Hedef tek ekran: 1600×1000'de kaydırma yok.
7. Simülasyon rakamları "Uygulama verisi · 1 aylık geçmiş" etiketiyle ve kaynakları (tahmini parametre, şube beyanı) belirtilerek sunulur.
