# Tasarım: Durak bilgi kartları ve yaklaşma tetiği

## Bileşenler

| Dosya | Ne |
|---|---|
| `agents/rundata.py` | `INFO_KINDS`, `MEMORY_KINDS = QUIRK_KINDS + INFO_KINDS` |
| `agents/guardrails.py` | `SECRET` kalıbı, `find_secret`, `redact_secret` |
| `agents/memorybook.py` | `upsert`: bilgi türünde metin zorunlu; şifre içeren metin `MemoryWriteError` |
| `agents/memory.py` | `INFO_KEYWORDS`, `classify` (rotayı etkileyen tür öncelikli), `info_text` (temizleme; "5. kat" sıra sayısı korunur) |
| `agents/route.py` | `MemoryConstraints._entries` bilgi türlerini süzer |
| `agents/cards.py` | `card_of`, `moment_of`, `affects_route`, `StopCards.items()`, `StopCards.approach()` |
| `api/main.py` | `GET /api/cards/{day}/{courier}`, `POST /api/approach` |

## Kararlar

- **Bilgi türleri rotaya girmez.** Simülatörde karşılıkları yoktur; etkilerini ölçemeyiz. Bu yüzden değerleri hakkında dakika ya da başarı iddiası yapılmaz ("kuryeye bilgi verir").
- **Çıplak "park" anahtar kelimesi yoktur.** "Parkın yanındaki apartman" gibi adres tarifleri park notu sayılmasın diye `park et`, `park yeri`, `otopark` gibi kalıplar aranır.
- **Eşikler** (`APPROACH_M = 400`, `DOOR_M = 60`, `SPEAK_MAX = 2`) tahminidir; pilotta ayarlanır.
- **Durumsuz tetik.** İstemci konumu, sıradaki durağı ve söylenmiş kartları gönderir. Sunucu yeniden başlasa kaybolacak durum yoktur; çağrı ~0,1 sn sürer.
- **Rota kaynağı.** Onaylı plan varsa o, yoksa simülasyon planı; duraklar hafızalı sırayla dizilir (brifingle aynı).

## Test

`agents/tests/test_cards.py` (5), `api/tests/test_cards_api.py` (2): sınıflandırma simülatör notlarını bozmaz · park notu kaydedilir, şifre ayıklanır, rota değişmez · şifre ve boş bilgi reddedilir · kart listesi yapılı ve sıralı, ikinci kaynak teyit eder · yaklaşma anları ve tekrar söylememe.

## Açık riskler

- Bilgi türlerinin değeri ölçülmedi. Pilotta: kartlı durakta kapı süresi ve "bulamadım" aramaları.
- Kurallı yol not başına tek tür yazar; canlı istem her tür için ayrı kayıt ister.
