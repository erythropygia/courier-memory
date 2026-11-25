# Veri haritası

Her veri dosyası nereden gelir, kim okur, gerçek mi uygulama verisi mi, git'te mi. Kurallar: `.kiro/steering/veri-kurallari.md`. Biçimler: `docs/sozlesmeler.md`.

## Güncel çalıştırma (yayımlanan)

| | Çalıştırma kimliği | Faz |
|---|---|---|
| Demo dönemi (20 gün, 4 senaryo) | `leave_wave+turnover+borrowed_courier+volume_shock-s42-00e214fe` | 6 |
| Uzun dönem (60 gün) | `long_term-s42-78a6f8c3` | 6 |

`data/demo_run/` bu iki çalıştırmanın yayımıdır (`data/demo_run/meta.json → run_id`, `data/demo_run/long_term/meta.json → run_id`). Faz 5'te tüm zincir yeniden koşuldu (demo → uzun dönem → Hedef 1 → ablasyon → tarama → yayım → maliyet → ekonomi → sunum rakamları); kalibrasyon 14/14; hikayenin `scene2.json` kümeleri ve `fallback.json` bu yayımdan. Sabah alanları: `summary.morning`, `arms.*.{departure_mean, end_mean}`, anlık görüntü rotası `departure`, D karşı-olgusu `current_morning`, `economics.morning` (§10).

`runs/` yalnız bu iki çalıştırmayı ve deney çıktılarını (öğrenme, ablasyon, tarama) tutar. Faz 2b dönemine ait iki eski çalıştırma (`…-8825e820`, `uzun_donem-s42-5f7db415`) Faz 4'te, Faz 2c dönemine ait iki çalıştırma (`…-2c70c4ff`, `uzun_donem-s42-f9d1ceb2`) Faz 5'te silindi (git geçmişinde).

## Dosyalar

| Yer | Ne | Üreten | Okuyan | Gerçek mi | Git |
|---|---|---|---|---|---|
| `sim/config/default.yaml`, `scenarios/*.yaml`, `sweep.yaml` | Parametreler, gerekçeleriyle | elle | `cm_sim` | simülasyon varsayımı | izli |
| `sim/config/calibration.yaml` | Kalibrasyon hedefleri | elle (saha özetinden) | `cm_sim.calibration` | **türetilmiş toplu** (yuvarlanmış; arayüze `target` gitmez) | izli |
| `runs/<id>/` | Simülasyon çıktısı (anlık görüntü, atama, hafıza, özet) | `cm_sim.run` | `cm_sim.publish` | uygulama verisi | izli (`c9feaaa`'da bilerek; `.gitignore` yenilerini dışarıda tutar) |
| `runs/learning/`, `runs/ablation/`, `runs/sweep_demo_s2/`, `runs/*.log` | Hedef 1, ablasyon, sağlamlık | `cm_sim.learning`, `cm_sim.ablation`, `cm_sim.sweep` | `cm_sim.publish` | uygulama verisi | izli |
| `data/demo_run/` | **Yayımlanan çalıştırma**: API ve ajanların tek veri kaynağı (`CM_RUN_DIR`) | `cm_sim.publish` | `api`, `agents` | uygulama verisi | izli |
| `data/demo_run/truth.json`, `notes_truth.json`, `snapshots/*/…` içindeki `truth` | Gizli gerçek | `cm_sim.publish` | yalnız değerlendirme (`agents.evaluate`, API'de "yalnız değerlendirme" etiketiyle) | uygulama verisi | izli |
| `data/demo_run/token_usage.json` | Ajan çağrısı başına token (tahmin; canlı ölçüm varsa ölçüm) | `agents.cost` | `agents.economics` | tahmin | izli |
| `data/demo_run/economics.json` | TL ekonomi | `agents.economics` | `/api/economics` (istek başına yeniden hesaplar) | VARSAYIM'lı | izli |
| `docs/sunum_rakamlari.md` | Sunum rakamlarının tek kaynağı | `agents.presentation_figures` | sunum, `docs/sunum.md` | uygulama verisi | izli |
| `data/live_memory.json` | Canlı adres hafızası | API çalışırken yazılır (not, hasat, geri bildirim) | API | uygulama verisi | izli ama `.gitignore`'da: **testler ve demo değiştirir; commit öncesi `git checkout --`** |
| `data/memory_evaluation.json` | Hafıza Ajanı doğruluk ölçümü | `agents.evaluate` | elle / sunum | ölçüm (mock'ta şablon) | izli, `.gitignore`'da |
| `data/agent_feed.json` | Ajan akışı (Hafıza, Değerlendirme, Bölge ajanlarının işleri, müdür kararları) | API çalışırken yazılır | API (`/api/feed`) | uygulama verisi | yok, `.gitignore`'da |
| `data/real_day/2026-05-05.json` | Beykoz 5 Mayıs: 18 BCS bölgesi, 22 kurye iş yükü, 19 dinamik küme (motor sırası), 2.058 durak (kuryenin bildiği/bilmediği), gerçek başarısızlık oranları (tanıdık %3,0 · yabancı %11,9; 13 iş günü), 1 aylık hafıza geçmişi (uygulama verisi) | `merged` dalındaki `tools/gercek_gun_hazirla.py` ← paket + gerçek coğrafyalı uzun dönem koşusu (gün 49); anahtarları Faz 7'de İngilizceye çevrildi | `agents.real_day`, `/api/real-day/*` | **GERÇEK** gönderi/nokta/oran (bölge kodu, kurye kimliği, barkod yok; kurye adları takma ad) + 1 aylık uygulama hafızası | izli |
| `data/map/osrm_real.json` | Gerçek günün durak→durak yol bacakları (polyline6, metre) | `merged` dalındaki `tools/osrm_gercek.py` (herkese açık OSRM sunucusu, yalnız koordinat) | `agents.real_day.RealDay.path` | üçüncü taraf yol verisi (© OpenStreetMap katkıcıları) | izli |
| `data/usage.jsonl` | Canlı token günlüğü | `CM_LLM_MODE=live\|record` | `agents.cost` | ölçüm | yok (etkinlikte oluşur), `.gitignore`'da |
| `cassettes/` | Kayıt-oynat LLM yanıtları | `CM_LLM_MODE=record` | `replay` modu | ölçüm | yok (etkinlikte) |
| `ui-story/data/scene1.json` | 18 sabit bölge, dinamik bölgeler, 4–5 Mayıs teslim noktaları, Sahne 1 rakamları | `ui-story/tools/prepare.py` ← paket | Sahne 1 | **GERÇEK** (kimlik, barkod, bölge kodu yok; koordinat 4 hane) | izli |
| `ui-story/data/sim_mapping.json` | Sim adresi → gerçek Beykoz teslim noktası (deterministik) | `prepare.py` | Sahne 2–5 | **gerçek konum** | izli |
| `ui-story/data/scene2.json` | Gün 32 kol D kümeleri ve durakları, olağan Çarşamba (gün 26) durakları | `prepare.py` ← `data/demo_run/snapshots` + paket sınırı | Sahne 2–3 | gerçek konum, uygulama verisi sonucu | izli |
| `ui-story/data/trace_fallback.json` | Sahne 2 kayıtlı orkestratör izi | `ui-story/tools/record_trace.py` (mock API) | Sahne 2 (API yoksa) | uygulama verisi | izli |
| `ui-story/data/fallback.json` | Sahne 3–7 kayıtlı yanıtları + demo seçimleri (`demo`) | `ui-story/tools/record_fallback.py` (mock API) | `CM.api` (API yoksa), `CM.demo` | uygulama verisi | izli |
| `ui-story/tiles/`, `fonts/`, `vendor/` | Vektör karolar, yazı tipleri, MapLibre | `tools/download_tiles.py`, elle | hikaye | üçüncü taraf (karolar © OpenMapTiles © OpenStreetMap katkıcıları, atıf her sahnede; Inter ve Barlow Condensed OFL, lisansları `fonts/`'ta; Noto Sans glyph'leri OFL; MapLibre BSD-3) | izli |
| `ui-yon/index.html` | Faz 3a tasarım yönü demosu, gömülü API çıktısı | elle (bir kez) | — | uygulama verisi, **dondurulmuş** (Faz 2b dönemi rakamları; güncellenmez) | izli |
| `docs/ekran_goruntuleri/` | Eski tek sayfanın referans görüntüleri; `story/` altında hikaye sahneleri | elle / başsız tarayıcı | spec, yeniden kurulum | uygulama verisi + gerçek konum | izli |
| `../courier-memory-paket/` (depo kökü) | Ham saha verisi, şirket içi adlar, karşılaştırma sayfası ve betikleri | — | yalnız `prepare.py` | **HAM GERÇEK** | izli; izinle repoyla paylaşılabilir (24 Kasım 2026) |

## Yeniden üretim zinciri

Kod ya da parametre değişince, sırayla (cwd `courier-memory-hackathon/`):

```bash
python -m cm_sim.run --demo --out runs
python -m cm_sim.run --scenario long_term --no-snapshots --out runs
python -m cm_sim.learning --seeds 12
python -m cm_sim.ablation --seeds 3
python -m cm_sim.sweep --seeds 2
python -m cm_sim.publish                       # → data/demo_run/
python -m agents.cost && python -m agents.economics && python -m agents.presentation_figures
pip install -e ".[story]" && python ui-story/tools/prepare.py      # → sahne1/sahne2/sim_eslesme (paket gerekir)
CM_LLM_MODE=mock uvicorn api.main:app --port 8000 &                   # temiz sunucu
python ui-story/tools/record_fallback.py http://127.0.0.1:8000          # → fallback.json (+ demo seçimleri)
python ui-story/tools/record_trace.py http://127.0.0.1:8000             # → trace_fallback.json
git checkout -- data/live_memory.json
```

Son dört adım atlanırsa hikaye hata vermez ama **yanlış gösterir** (Faz 3c'de bulundu: Faz 2c küme kimliklerini kaydırmıştı, Sahne 3 başka kuryenin bölgesini vurguluyordu). Çalıştırma kimliği değişirse bu sayfadaki tabloyu ve `docs/sunum.md` demo metnindeki ad/sayıları güncelleyin.

**Satır sonları:** Faz 0–2c dosyalarının bir kısmı Windows'ta CRLF üretildi (`api/main.py`, `data/demo_run/economics.json`, `token_usage.json`, `docs/sunum_rakamlari.md` …). Linux'ta yeniden üretince yalnız satır sonu farkı çıkar; içerik aynıysa `git checkout --` ile geri alın, düzenlerken CRLF'yi koruyun.
