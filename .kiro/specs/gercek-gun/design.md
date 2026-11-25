# Tasarım: Gerçek gün

| Dosya | Ne |
|---|---|
| `data/real_day/2026-05-05.json` | 18 bölge, 22 kurye, 19 küme, 2.058 durak, oranlar (tanıdık %3,0 · yabancı %11,9; 13 iş günü), 1 aylık hafıza geçmişi (uygulama verisi) |
| `data/map/osrm_real.json` | Durak → durak yol bacakları (polyline6, metre) |
| `agents/real_day.py` | `RealDay.memory_summary`, `cluster`, `transfer`, `path`; `decode6` |
| `agents/stop_order.py` | `route_order`: motor sırasını kümenin duraklarına bağlar |
| `api/main.py` | `GET /api/real-day/{day}` ve `/memory`, `/cluster/{cid}`, `/transfer` |

## Kararlar

- **Veri hazır gelir.** Dosyalar `merged` dalındaki üretici araçların çıktısıdır; anahtarları Faz 7'de İngilizceye çevrildi. Üretici araçlar gerçek coğrafyalı simülasyon koşusuna bağlı olduğu için master'a alınmadı (`docs/veri-haritasi.md`).
- **Simülasyon soyut dünyada kalır.** Gerçek duraklar simülasyon adreslerine 15 m içinde eşlenir; soyut dünyada eşleşme yoktur. Kartlar yalnız dosyadaki geçmişten gelir, oturumda eklenen not gerçek güne yansımaz.
- **Dürüst etiketler.** Kapsam hesabı "kapsanan durakta ipucu tam etkili" varsayar; aktarım dengesi yaklaşıktır. İkisi de sonuçta metin olarak döner.

## Test

`agents/tests/test_review.py::test_real_day_memory_and_transfer`, `api/tests/test_review_region_api.py::test_real_day_endpoints`.
