# Tasarım: Sabah akışı

- **Simülatör** (`cm_sim`): `config.Morning`; `rng.S_MORNING = 22`; `engine`: `_morning_min(arm)`, `_plan_start(arm)` (beklenen), `_deviation(gün)` (kurye başına, önbellekli), `_departure(kol, gün, kurye, mins=None)`; `execute_route(..., start=)`; `RouteResult.start_minute`; `shift_end_at(cfg)`; günlük ölçüler `overtime_minutes` (vardiya bitişinden), `departure_mean`, `end_mean`. Karşı-olgular D'nin gerçek çıkışıyla yürür (yalnız hafıza değişir); `current_morning` aynı rotayı bugünkü sabahla yürütür. `export.morning_summary`; anlık görüntüde rota `departure`.
- **Deneyler:** `sweep.yaml → fixed` ve `learning` sabahı eşitler; `ablation.EQUAL_MORNING` hafıza varyantlarına eklenir, `full_morning` hariç; `PAIRS["morning"] = (full_morning, full)`.
- **Ajan:** `_routing_cfg` → `morning`, `shift_end_at`; `RoutePlanner.rc["start"] = plan_departure(morning, arm)`; `DayTools.sorting_plan`, `morning_summary`; kurallı sıra `… compute_route → sorting_plan → present_proposal`; istem adım 7.
- **API:** `/api/morning/{gün}`, `/api/morning/scan` (`_morning_tools`: onaylı plan varsa onun ataması).
- **Ekonomi:** `summary.morning.counterfactual.daily` ile `D_current` (D'nin başarısız ve fazla mesaisi bugünkü sabahla); şelale `hafiza = D_current − C`, `sabah = D − D_current`.
- **Hikaye:** `scene3.js → unload()`; `scene2.js` `sorting_plan` vuruşu; `scene7.js` şelale etiketi; `story.css` raf ızgarası.
