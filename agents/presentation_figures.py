"""Sunum rakamlarını verilerden üretir: python -m agents.presentation_figures → docs/sunum_rakamlari.md

Canlı ölçümden sonra (degerlendir → simülasyon → publish → maliyet → ekonomi) tek komutla güncellenir;
sunum ile demo arasında rakam tutarsızlığı kalmaz.
"""
from __future__ import annotations

import json
from pathlib import Path

from .rundata import ROOT, RunData
from .tr import hhmm, name_dative, num
# Türkçe okuyucuya giden ham kodların etiketleri (kod İngilizce, belge Türkçe).
ADDRESS_TYPE_TR = {"house": "müstakil ev", "apartment": "apartman", "site": "site", "workplace": "iş yeri",
                   "collection_point": "toplu teslim noktası"}
LEVEL_TR = {"low": "düşük", "mid": "orta", "high": "yüksek"}
SOURCE_TR = {"estimate": "tahmin", "measurement": "ölçüm"}


def _pct(x: float, nd: int = 1) -> str:
    return "%" + num(100 * x, nd)


def _spct(x: float, nd: int = 1) -> str:
    """İşaretli yüzde (zaten yüzde birimli değer): −%53,6 / +%2,0"""
    return ("−" if x < 0 else "+") + "%" + num(abs(x), nd)


def _val(v: float) -> str:
    return num(v, 0) if abs(v) >= 100 else num(v, 3) if abs(v) < 1 else num(v, 2)


def main() -> int:
    run = RunData()
    d = run.dir
    S = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    U = json.loads((d / "long_term" / "summary.json").read_text(encoding="utf-8")) if (d / "long_term" / "summary.json").exists() else None
    E = json.loads((d / "economics.json").read_text(encoding="utf-8")) if (d / "economics.json").exists() else None
    W = json.loads((d / "sweep.json").read_text(encoding="utf-8")) if (d / "sweep.json").exists() else None
    K = json.loads((d / "calibration.json").read_text(encoding="utf-8")) if (d / "calibration.json").exists() else None
    R = json.loads((d / "recovery.json").read_text(encoding="utf-8"))
    OG = json.loads((d / "learning.json").read_text(encoding="utf-8")) if (d / "learning.json").exists() else None
    AB = json.loads((d / "ablation.json").read_text(encoding="utf-8")) if (d / "ablation.json").exists() else None
    m = run.meta
    L: list[str] = ["# Sunum rakamları (otomatik üretildi)", "",
                    f"> Kaynak: `data/demo_run/` · çalıştırma `{run.run_id}` · **Uygulama verisi · 1 aylık geçmiş**; tahmini parametrelerle.", ""]

    def table(summ: dict, title: str) -> None:
        A = summ["arms"]
        L.extend([f"## {title}", "", "| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Vardiya bandında | İş yükü sapması | Hafıza kapsamı |",
                  "|---|---|---|---|---|---|---|"])
        for a in "ABCD":
            x = A[a]
            L.append(f"| {a} · {x['label']} | {_pct(x['first_attempt_rate'], 2)} | {num(x['preventable_fail'], 0)} | {num(x['couriers_per_day'], 1)} | "
                     f"{_pct(x['in_band_share'], 0)} | {_pct(x['workload_cv'], 0)} | {_pct(x['memory_coverage'], 1)} |")
        dl = summ["deltas"]
        L.extend(["", f"- C ← B (uyumlu atama): ilk denemede teslim {num(dl['C_vs_B']['first_attempt_pp'], 2, True)} puan, önlenebilir başarısızlık {_spct(dl['C_vs_B']['preventable_fail_pct'])}",
                  f"- D ← C (hafıza + brifing): {num(dl['D_vs_C']['first_attempt_pp'], 2, True)} puan, önlenebilir başarısızlık {_spct(dl['D_vs_C']['preventable_fail_pct'])}",
                  f"- D ← A (yeni yapı + hafıza vs mevcut yapı): araç-gün {_spct(dl['D_vs_A']['vehicle_days_pct'])}, ilk denemede teslim {num(dl['D_vs_A']['first_attempt_pp'], 2, True)} puan",
                  f"- B ← A (yeni yapı, ajansız): ilk denemede teslim {num(dl['B_vs_A']['first_attempt_pp'], 2, True)} puan", ""])

    if U:
        table(U, "Uzun dönem (60 iş günü): manşet")
        A, Dd = U["arms"]["A"], U["arms"]["D"]
        L.extend(["**Manşet cümlesi:** Yeni yapı + Courier Memory, mevcut yapının ilk denemede teslim kalitesini "
                  f"({_pct(A['first_attempt_rate'], 1)} → {_pct(Dd['first_attempt_rate'], 1)}) "
                  f"{_pct(1 - Dd['couriers_per_day'] / A['couriers_per_day'], 0)} daha az kuryeyle ve dengeli iş yüküyle "
                  f"(iş yükü sapması {_pct(A['workload_cv'], 0)} → {_pct(Dd['workload_cv'], 0)}; vardiya bandında {_pct(A['in_band_share'], 0)} → {_pct(Dd['in_band_share'], 0)}) korur.", ""])
    table(S, f"Demo dönemi (20 iş günü, senaryolar: {', '.join(m['scenarios'])})")
    c = m["critical"]
    L.extend([f"**Demo anı:** gün {c['day']} ({run.weekday_name(c['day'])}), kurye {c['courier_name']} ({c['courier']}).", ""])
    try:                                                   # Hedef 2: "kim gitsin" (Orkestratör araçları, LLM'siz)
        import tempfile

        from .memorybook import MemoryBook
        from .orchestrator import DayTools
        with tempfile.TemporaryDirectory() as td:
            ar = DayTools(run, MemoryBook(run, Path(td) / "m.json"), c["day"])
            container = ar.capacity_gap({})
            res = ar.neighbor_candidates({"need": container["shortfall"], "exclude": [], "current_borrowed": []})
        L.extend([f"## Kim gitsin (Hedef 2) · gün {c['day']}: {container['required_courier_day']} kurye-gün gerekli, yerelde {container['local_available']} → açık "
                  f"{container['shortfall']}", "", "| Sıra | Aday | Aldığı kümede tanıdık durak | Hafıza kapsamı (yabancı durak) | Beklenen dk | Plan maliyeti |",
                  "|---|---|---|---|---|---|"])
        for x in res["candidates"]:
            L.append(f"| {x['order']} | {x['name']} | {_pct(x['familiar_share'], 0)} | {_pct(x['memory_coverage'], 0)} | {x['expected_min']} | {num(x['plan_cost'], 1)} |")
        L.extend(["", f"Önerilen: {', '.join(run.courier_name(i) for i in res['proposed'])}; eşitlik: {'var' if res['tie'] else 'yok'}. {res['rationale']}", ""])
    except Exception as e:  # rakam üretimi sunumu durdurmasın
        L.extend([f"(Kim gitsin tablosu üretilemedi: {e})", ""])
    hk = c.get("memory_gain")
    if hk:
        L.extend([f"**Hafıza {name_dative(c['courier_name'])} {num(hk['mins'], 0)} dk kazandırdı** (aynı kurye, aynı duraklar, aynı gün: hafızasız "
                  f"{num(hk['memoryless_min'], 0)} dk → yalnız kapı ipucu {num(hk['hint_only_min'], 0)} → hafızalı {num(hk['memory_min'], 0)} dk; "
                  f"başarısız {hk['fails_memoryless']} → {hk['fails_memory']}). Tek rota, tek gün: aşağıdaki dağılımla birlikte söyleyin.", ""])
    mr = S.get("memory_routing") or {}
    if mr.get("daily"):
        g = mr["daily"]
        L.extend(["## Hafıza rotayı değiştirir (Hedef 3) · kol D, aynı rota karşı-olgusu, şube-gün ortalaması", "",
                  "| | Hafızasız | Yalnız kapı ipucu | Hafızalı (ipucu + rota) |", "|---|---|---|---|"])
        for k, res, nd in (("minutes", "Toplam rota dakikası", 0), ("km", "km", 1), ("preventable_fail", "Bilgiyle önlenebilir başarısız", 1),
                          ("window_hits", "Kapalı penceresine (öğle) denk gelen varış", 1), ("window_wait", "Öğle arası bekleme dk", 0),
                          ("wasted", "Kapalı kapıya gidiş", 1)):
            L.append(f"| {res} | {num(g['memoryless'][k], nd)} | {num(g['hint_only'][k], nd)} | {num(g['memory'][k], nd)} |")
        L.extend(["", "Kurye türüne göre rota başına hafıza kazancı (dk; hafızasız − hafızalı; p10 / medyan / p90):", ""])
        TR = {"borrowed": "Ödünç", "new": "Yeni", "reserve": "Yedek", "senior": "Kıdemli"}
        for kd in ("borrowed", "new", "reserve", "senior"):
            x = (mr.get("type") or {}).get(kd)
            if x:
                L.append(f"- {TR[kd]} ({x['route']} rota-gün): ort. {num(x['min_gain_route_mean'], 0)} dk ({num(x['min_gain_route_p10'], 0)} / "
                         f"{num(x['min_gain_route_p50'], 0)} / {num(x['min_gain_route_p90'], 0)}); bunun rota payı {num(x['route_share_min_route_mean'], 1)} dk; "
                         f"önlenen başarısız {num(x['prevented_fails_route_mean'], 2)}/rota")
        Name = S["arms"]["D"]
        L.extend(["", f"- Planda erteleme (iki kaynakla teyitli kapanış): {Name.get('plan_deferred_stops', 0)} durak, bunun "
                      f"{Name.get('wrong_deferrals', 0)}'i yanlış (açık çıktı; başarısız sayıldı).",
                  f"- ETA hatası (|gerçekleşen − planlanan|, rota başına): C {num(S['arms']['C'].get('eta_abs_error', 0), 0)} dk → "
                  f"D {num(Name.get('eta_abs_error', 0), 0)} dk (hafızadaki ek servis süresi plana girdiği için).", ""])
    zs = [(lbl, x["time_analysis"]) for lbl, x in (("Demo (20 gün)", S), ("Uzun dönem (60 gün)", U)) if x and (x.get("time_analysis") or {}).get("day")]
    if zs:
        L.extend(["## Teslim zamanı analizi (kayıtlardan, notsuz) · kol D, aynı rota: zaman onarımı var ↔ yok, şube-gün", "",
                  "| | Rotaya alınan bulgu/gün | Taşınan durak/gün | Bulgu doğruluğu (gizli gerçek) | Alıcı yok (gönderi/gün) | Tekrar ziyaret (durak/gün) | km/gün | Fazla mesai dk/gün | Beklenen rota süresi dk/gün | Taşınan duraklarda başarısız |",
                  "|---|---|---|---|---|---|---|---|---|---|"])
        for lbl, z in zs:
            f, g, tv = z["diff_daily"], z["daily"], z["carried_stops"]
            L.append(f"| {lbl} | {num(g['route'], 1)} | {num(g['carried'], 1)} | {_pct(z['accuracy'] or 0, 0)} | {num(f['recipient_absent'], 2, True)} | "
                     f"{num(f['revisit'], 2, True)} | {num(f['km'], 2, True)} | {num(f['overtime_min'], 1, True)} | "
                     f"{num(f.get('expected_duration_min', 0), 1, True)} | {tv['fails_no_time']} → {tv['fails_memory']} ({tv['stop']} durak) |")
        L.append("")
        for lbl, z in zs:
            k, al = z.get("constraint") or {}, z.get("alternatives") or {}
            if k.get("route"):
                select = al.get("option") or {}
                L.append(f"- Sert kısıt, {lbl}: {k['route']} rotada ihlal {k['violation']}, yeni bant üstü {k['new_over_band']}; onarım "
                         f"öncesine göre en çok {num(k['max_duration_diff_min'], 1, True)} dk ve {num(k['max_km_diff'], 2, True)} km "
                         f"(tolerans {num(k['tolerance_min'], 0, True)} dk / {num(k['tolerance_km'], 1, True)} km). Kısıt yüzünden aynı rotada "
                         f"kaydırılamayan {al.get('total', 0)} bulgu: aktarma {select.get('transfer', 0)}, ertesi gün {select.get('next_day', 0)}, "
                         f"akşam/teslim noktası {select.get('evening_delivery_point', 0)} önerisi (+SMS; müdür kararı, uygulanmadı).")
        if AB and AB.get("time_contribution"):
            L.append("")
            for g, lbl in (("g20", "20 günlük geçmiş"), ("g60", "60 günlük geçmiş (duyarlılık)"), ("tol5", "tolerans +5 dk (duyarlılık)"),
                           ("unconstrained_2_b", "kısıtsız (eski)")):
                x = AB["time_contribution"].get(g)
                if x:
                    ar = (f"; aynı rota: alıcı yok {num(x['same_route_recipient_absent']['mean'], 2, True)}, fazla mesai "
                          f"{num(x['same_route_overtime_min']['mean'], 1, True)} [{num(x['same_route_overtime_min']['min'], 1, True)}, "
                          f"{num(x['same_route_overtime_min']['max'], 1, True)}] dk, beklenen rota süresi {num(x['same_route_expected_min']['mean'], 1, True)} "
                          f"[en çok {num(x['same_route_expected_min']['max'], 1, True)}] dk/gün") if "same_route_expected_min" in x else "" if "same_route_recipient_absent" in x else ""
                    L.append(f"- Ablasyon, {lbl} ({AB['seeds']} seed, tam − zamansız): alıcı yok {num(x['recipient_absent_D']['mean'], 2, True)} "
                             f"[{num(x['recipient_absent_D']['min'], 2, True)}, {num(x['recipient_absent_D']['max'], 2, True)}]/gün, tekrar ziyaret "
                             f"{num(x['revisit_D']['mean'], 2, True)}, km {num(x['km_D']['mean'], 2, True)}, fazla mesai {num(x['overtime_D']['mean'], 1, True)} dk/gün, "
                             f"ilk denemede {num(x['D_far_pct']['mean'], 3, True)} puan" + ar)
        zx = m.get("time_example")
        if zx:
            b, ch, so = zx["finding"], zx["change"], zx["result"]
            hist = ", ".join(f"{g['weekday']} {g['hour']} {'✗' if g['result'] == 'recipient_absent' else '✓'}" for g in zx["history"])
            L.extend(["", f"**Demo örneği (seçilmiş; büyüklük yukarıdaki tablo):** gün {zx['day']} ({zx['weekday']}), {zx['courier_name']}, "
                          f"{zx['label']} ({ADDRESS_TYPE_TR.get(zx['address_type'], zx['address_type'])}). Geçmiş {len(zx['history'])} deneme: {hist}. Bulgu: {b['text']} (güven {LEVEL_TR.get(b['level'], b['level'])}, "
                          f"P = {num(b['confidence'], 3)}). Rota: {ch['old_order']}. → {ch['new_order']}. sıra, tahmini bulunamama %{round(100 * ch['old_p'])} → "
                          f"%{round(100 * ch['new_p'])}, {num(ch['extra_km'], 2, True)} km, rota süresi {num(ch.get('extra_min', 0), 1, True)} dk. Aynı gün, aynı rastgele sayılar: zamansız {so['no_time']['arrival']} "
                          f"{so['no_time']['result']} → zaman-farkında {so['memory']['arrival']} {so['memory']['result']}"
                          + (f"; rota fazla mesaisi {num(zx['route']['overtime_min']['no_time'], 0)} → {num(zx['route']['overtime_min']['memory'], 0)} dk."
                             if zx.get("route") else ".")])
        zk = m.get("time_example_constraint")
        if zk:
            L.extend(["", f"**Kısıt örneği (seçilmiş):** gün {zk['day']} ({zk['weekday']}). {zk['text']}"])
        L.extend(["", "- Dürüstlük: gerçek Beykoz verisinde başarısızlık saati ve nedeni boş; bu etki gerçek veriyle kanıtlanamaz. Simülasyonda "
                      "**mekanizma** olarak gösterilir (bulunabilirlik profilleri tahminidir); büyüklüğü pilot ölçer.", ""])
    hv = S.get("harvest")
    if hv and hv.get("day"):
        L.extend(["## Bilgi hasadı (kol D, simülasyon)", "",
                  f"- {hv['day']} günde {hv['question']} hedefli soru (günde ~{num(hv['question'] / hv['day'], 0)}; {hv['handover']}'i ayrılan kuryeye devir "
                  f"teslim sorusu), {hv['answer']} cevap, {hv['record']} yeni hafıza kaydı. Soruların çoğu \"bildiğim sorun yok\" ile döner "
                  f"({hv['no_info']}); bu, adreslerin çoğunda püf noktası olmadığı içindir.", ""])
    if OG:
        w, pr, u = OG["first_week"], OG["first_week_paired_diff_C_minus_D"], OG["mastery_day"]
        ci = lambda t, nd=1: f"{num(t[0], nd)} [{num(t[1], nd)} – {num(t[2], nd)}]"  # noqa: E731
        L.extend([f"## Yeni kuryenin ilk haftası (Hedef 1) · işe alım deneyi, {len(OG['seeds'])} seed × 4 yeni kurye", "",
                  f"- İlk 6 iş gününde bilgiyle önlenebilir başarısız teslim (kurye başına): hafızasız (C) {ci(w['C']['preventable_fails'])}, "
                  f"hafızalı (D) {ci(w['D']['preventable_fails'])}; **eşli fark (aynı kurye, aynı seed) {ci(pr['preventable_fails'])}** (%95 aralık).",
                  f"- İlk hafta rota dakikası farkı (C − D): {ci(pr['route_min'], 0)} dk.",
                  f"- Ustalaşma günü ({u['threshold']}): C {u['C']} · D {u['D']}. Gürültülü bir ölçü; manşette ilk hafta farkını kullanın.", ""])
    if AB:
        V = AB["variants"]
        names = {"hint_only": "Yalnız kapı ipucu (öğle düzeltmesiyle)", "hint_harvest": "+ hasat", "hint_route": "+ hafıza-farkında rota",
                 "full": "İpucu + hasat + rota + zaman analizi (yayımlanan D)", "no_time": "Tam − teslim zamanı analizi",
                 "unconstrained": "Tam, sert kısıt kapalı (eski)",
                 "full_morning": "Tam + sabah (ayrıştırma okutmada; D − C sabahı da içerir)"}
        L.extend([f"## Hafızanın katkısı parça parça (demo senaryoları × {AB['seeds']} seed; ort. [min, max])", "",
                  "| Varyant | D − C ilk denemede (puan) | Önlenebilir başarısız (D/C) | Fazla mesai D − C (dk/gün) | km D − C |", "|---|---|---|---|---|"])
        for k, res in names.items():
            x = V.get(k)
            if x:
                L.append(f"| {res} | {num(x['D_vs_C_pp']['mean'], 2, True)} [{num(x['D_vs_C_pp']['min'], 2, True)}, {num(x['D_vs_C_pp']['max'], 2, True)}] | "
                         f"{_spct(x['D_vs_C_preventable_pct']['mean'])} | {num(x['overtime_D_minus_C']['mean'], 0, True)} | {num(x['km_D_minus_C']['mean'], 1, True)} |")
        L.append("")

    def morning_row(summ: dict | None, res: str) -> None:
        ko = ((summ or {}).get("morning") or {}).get("counterfactual")
        if not ko:
            return
        g, f = ko["daily"], ko["diff_daily"]
        h, b = g["memory"], g["current_morning"]
        L.extend([f"**{res}** ({ko['day']} gün, şube-gün ortalaması)", "",
                  "| | Ayrıştırma okutmada (D) | Aynı rota, bugünkü sabahla | Fark |", "|---|---|---|---|",
                  f"| Ortalama çıkış | {hhmm(h['departure_mean'])} | {hhmm(b['departure_mean'])} | {num(f['departure_mean'], 0, True)} dk |",
                  f"| Ortalama dönüş | {hhmm(h['return_mean'])} | {hhmm(b['return_mean'])} | {num(f['return_mean'], 0, True)} dk |",
                  f"| Vardiya bitişinden sonra dönen rota | {_pct(h['after_shift_returning_share'], 0)} | {_pct(b['after_shift_returning_share'], 0)} | "
                  f"{num(100 * f['after_shift_returning_share'], 0, True)} puan |",
                  f"| Fazla mesai dk/gün | {num(h['overtime_min'], 0)} | {num(b['overtime_min'], 0)} | {num(f['overtime_min'], 0, True)} |",
                  f"| Başarısız teslim/gün | {num(h['fail'], 1)} | {num(b['fail'], 1)} | {num(f['fail'], 1, True)} |",
                  f"| … alıcı yok | {num(h['recipient_absent'], 1)} | {num(b['recipient_absent'], 1)} | {num(f['recipient_absent'], 1, True)} |", ""])

    sb = S.get("morning") or {}
    if sb.get("enabled"):
        mb = sb["shift_start"]
        L.extend(["## Sabah: ayrıştırma indirme okutmasında · kol D, aynı rota bugünkü sabahla", "",
                  f"- Şube beyanı (pilot ölçer): mesai {hhmm(mb)}; bugünkü süreç (indirme → kurye kendi ayrıştırır → zimmet → yükleme) "
                  f"{num(sb['current_min'], 0)} dk → çıkış ~{hhmm(mb + sb['current_min'])}; ayrıştırma okutmaya gömülünce {num(sb['presorted_min'], 0)} dk → "
                  f"~{hhmm(mb + sb['presorted_min'])}; kurye başına sapma σ {num(sb['deviation_min'], 0)} dk. Vardiya bitişi {hhmm(sb['shift_end'])}; "
                  f"fazla mesai bu saatten sayılır.", "",
                  "- Karşı-olgu: kol D'nin aynı planı, ipuçları ve rastgele sayıları; yalnız çıkış saati bugünkü sabahla. Hafızanın katkısını ölçen "
                  "deneyler (tarama, öğrenme, ablasyonun hafıza varyantları) sabahı tüm kollarda eşit tutar.", ""])
        morning_row(U, "Uzun dönem (60 iş günü)")
        morning_row(S, "Demo dönemi (20 iş günü)")
        zk = ((AB or {}).get("time_contribution") or {}).get("morning")
        if zk:
            L.extend([f"- Ablasyon (tam + sabah − tam, aynı seed, {AB['seeds']} seed): fazla mesai {num(zk['overtime_D']['mean'], 0, True)} dk/gün "
                      f"[{num(zk['overtime_D']['min'], 0, True)}, {num(zk['overtime_D']['max'], 0, True)}], dönüş {num(zk['return_D']['mean'], 0, True)} dk, "
                      f"alıcı yok {num(zk['recipient_absent_D']['mean'], 2, True)} [{num(zk['recipient_absent_D']['min'], 2, True)}, {num(zk['recipient_absent_D']['max'], 2, True)}]/gün, "
                      f"ilk denemede {num(zk['D_far_pct']['mean'], 3, True)} puan. Fazla mesai ve dönüş karşı-olguyla aynı; teslim tarafında fark yok "
                      f"(aralık sıfırı kapsıyor). **Sağlam olan fazla mesai ve dönüş; teslim etkisi belirsiz, sunumda iddia etmeyin.**", ""])
        if E and E.get("morning"):
            es = E["morning"]
            L.extend([f"- Ekonomi: sabah kalemi günde {num(es['tl_day'], 0)} TL, yılda {num(es['tl_year'] / 1e6, 1)} mn TL (fazla mesai "
                      f"{num(es['overtime_min_day'], 0)} dk/gün daha az → {num(es.get('overtime_tl_day', 0), 0)} TL; başarısız {num(es['fails_per_day'], 1)}/gün daha az → "
                      f"{num(es.get('fails_tl_day', 0), 0)} TL). Erken çıkışın vardiya içinde "
                      f"açtığı kapasite (daha az kurye ihtiyacı) para değerine çevrilmedi.", ""])

    if E and "operation" in E:
        O, M = E["operation"], E["headline"]
        own = {a: 1 - (U or S)["arms"][a]["unfamiliar_share"] for a in "ABCD"}
        K3 = [("A", "Bugün (sabit bölge)"), ("B", "Yeni yapı, ajansız"), ("D", "Yeni yapı + Courier Memory")]
        L.extend(["## Operasyon maliyeti (manşet, şube başına, " + E["source_running"] + f" ortalaması)", "",
                  f"**{M['sentence']}**", "",
                  "| | " + " | ".join(n for _, n in K3) + " |", "|---|" + "---|" * len(K3)])
        rows = [("Kurye/gün", lambda x, a: num(x["courier"], 1)),
                ("Kendi bölgesinde durak payı", lambda x, a: _pct(own[a], 0)),
                ("Başarısız teslim/gün", lambda x, a: num(x["fails_per_day"], 0)),
                ("Fazla mesai saat/gün", lambda x, a: num(x["overtime_hour_day"], 0)),
                ("Operasyon maliyeti TL/gün", lambda x, a: num(x["total_tl_day"], 0)),
                ("Gönderi başına TL", lambda x, a: num(x["per_shipment_tl"], 2)),
                ("Yıllık fark (bugüne göre)", lambda x, a: "—" if a == "A" else
                 ("+" if x["total_tl_year"] > O["arms"]["A"]["total_tl_year"] else "−") + num(abs(x["total_tl_year"] - O["arms"]["A"]["total_tl_year"]) / 1e6, 1) + " mn TL")]
        for name, fn in rows:
            L.append(f"| {name} | " + " | ".join(fn(O["arms"][a], a) for a, _ in K3) + " |")
        L.extend(["", "**Şelale (TL/gün):** " + " → ".join(f"{x['step']} {('' if x['type'] in ('start', 'result') else ('+' if x['tl_day'] > 0 else '−'))}{num(abs(x['tl_day']), 0)}"
                                                       for x in O["waterfall"]),
                  "", "**Ölçek (yıllık operasyon tasarrufu):** " + "; ".join(f"{o['branch']} şube → {num(o['savings_tl_year'] / 1e6, 1)} mn TL" for o in O["scale"]), ""])
        if E.get("llm_scenarios"):
            L.extend(["**LLM senaryoları:** " + "; ".join(f"{x['name']}: {num(x['llm_tl_day'], 1)} TL/gün, {num(x['per_shipment_kurus'], 2)} kuruş/gönderi, "
                                                       f"tasarrufun %{num(100 * x['savings_rate'], 2)}'si" for x in E["llm_scenarios"]), ""])
    if E:
        Lm, vc, vb = E["llm"], E["gain"]["vs_C"], E["gain"]["vs_B"]
        L.extend(["## Ajanların maliyeti ve getirisi (temkinli senaryo, şube-gün, " + E["source_running"] + f" ortalaması, {E['day_count']} gün)", "",
                  f"- Hacim: {num(E['volume_day']['shipment'], 0)} gönderi, {num(E['volume_day']['courier'], 1)} kurye, {num(E['volume_day']['note'], 1)} not, "
                  f"{num(E['volume_day']['llm_call'], 0)} ajan çağrısı/gün",
                  f"- **LLM maliyeti: {num(Lm['daily_tl'], 0)} TL/gün · gönderi başına {num(Lm['per_shipment_kurus'], 1)} kuruş** "
                  f"(not başı {num(Lm['per_note_tl'], 2)} TL, brifing başı {num(Lm['per_briefing_tl'], 2)} TL; token kaynağı: "
                  f"{', '.join(sorted({SOURCE_TR.get(v['source'], v['source']) for v in Lm['agents'].values()}))})",
                  f"- **Hafıza + Brifing'in katkısı (C'ye göre, manşet):** günde {num(vc['prevented_fails_day'], 1)} başarısız teslim ve "
                  f"{num(vc['prevented_overtime_min_day'], 0)} dk fazla mesai daha az → doğrudan {num(vc['direct_gain_tl_day'], 0)} TL/gün, "
                  f"net {num(vc['net_tl_day'], 0)} TL/gün, **getiri {num(vc['return_multiple'], 1)}×**; ayrıca {num(vc['capacity_courier_hour_day'], 1)} kurye-saat/gün kapasite",
                  f"- Üç ajanın birlikte katkısı (B'ye göre, üst sınır): günde {num(vb['prevented_fails_day'], 1)} başarısız teslim daha az, getiri {num(vb['return_multiple'], 0)}×",
                  f"- Şube başına yıllık: LLM {num(E['branch_annual']['llm_tl'], 0)} TL, net kazanç (C'ye göre) {num(E['branch_annual']['net_tl_vs_C'], 0)} TL",
                  "- Ölçek: " + "; ".join(f"{o['branch']} şube → net {num(o['net_tl_year_vs_C'] / 1e6, 1)} milyon TL/yıl" for o in E["scale"]),
                  "- Model kaldıracı (bilgi): " + "; ".join(f"{x['name']} {num(x['llm_tl_day'], 0)} TL/gün ({num(x['per_shipment_kurus'], 2)} kuruş/gönderi)"
                                                          for x in E["model_comparison"]),
                  f"- Parametreler (tahmini; şirket rakamıyla değiştirin): kurye-gün {num(E['assumptions']['courier_daily_cost_tl'], 0)} TL, "
                  f"başarısız deneme {num(E['assumptions']['failed_attempt_tl'], 0)} TL, kur {num(E['assumptions']['usd_try'], 1)}, "
                  f"önbellek {'açık' if E['assumptions']['cache'] else 'kapalı (temkinli)'}", ""])
    if W:
        pp = [r["pp"]["D_vs_C"] for r in W["rows"]]
        h = W.get("headline")
        L.extend(["## Sağlamlık", ""])
        if h:
            a = h["D_vs_A_pp"]
            L.extend([f"- {len(W['rows'])} parametre kombinasyonu × {W['seeds']} seed. **Yeni yapı + hafıza (D) bugüne (A) göre ilk denemede teslim: "
                      f"{num(a['min'], 2, True)} … {num(a['max'], 2, True)} puan** (medyan {num(a['median'], 2, True)}; kombinasyonların "
                      f"%{num(100 * a['share_abs_le_0_15'], 0)}'inde ±0,15 puan içinde, %{num(100 * a['share_ge_0'], 0)}'inde ≥ 0; seed'ler arası yayılım "
                      f"ort. {num(a['seed_spread_mean'], 2)} puan), kurye-gün {num(h['courier_day_D_vs_A_pct']['min'], 1, True)} … "
                      f"{num(h['courier_day_D_vs_A_pct']['max'], 1, True)}%.",
                      f"- **Hafızanın katkısı (D − C): {num(h['D_vs_C_pp']['min'], 2, True)} … {num(h['D_vs_C_pp']['max'], 2, True)} puan**, "
                      f"kombinasyonların %{num(100 * h['D_vs_C_pp']['share_gt_0'], 0)}'inde pozitif.",
                      f"- (\"D ≥ C ≥ B\" %{num(100 * W['order_share'], 0)}: B rastgele atama olduğu için önemsiz; manşet değil.)", ""])
        else:
            L.extend([f"- Hafızanın katkısı (D − C): {num(min(pp), 2)} … {num(max(pp), 2)} puan", ""])
    if K:
        ok = sum(r["compatible"] for r in K["rows"])
        L.extend(["## Kalibrasyon", "", f"- Uygulama verisi saha verisinden türetilmiş toplu hedeflere uyumlu: **{ok}/{len(K['rows'])}**",
                  *(f"  - {r['explanation']}: uygulama {_val(r['value'])} {'✓' if r['compatible'] else '✗'}" for r in K["rows"]),
                  "  (Hedef değerler şirket içi toplu özettir; sunumda gösterilmez.)", ""])
    rc = R["end_of_eval_C"]
    L.extend(["## Kurye–bölge uyumu tahmincisi", "",
              f"- Gizli gerçek beceriyle sıra korelasyonu {num(rc['spearman_estimate'], 2)} (bölgeden arındırılmamış ham oran {num(rc['spearman_naive'], 2)}).", ""])
    out = ROOT / "docs" / "sunum_rakamlari.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
