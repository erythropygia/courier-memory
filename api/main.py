"""Courier Memory API: arayüz ↔ ajanlar ↔ çalıştırma klasörü (docs/sozlesmeler.md §4).

uvicorn api.main:app --reload     (CM_LLM_MODE=mock|live|record|replay, CM_RUN_DIR=data/demo_run)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import Services
from api import agentcore_chain, transcribe
from api.live import LIVE, LiveBusy

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"
UI_LEGACY = UI_DIR / "legacy"
UI_STORY = UI_DIR / "story"
UI_FLOW = UI_DIR / "flow"
UI_DEMO = UI_DIR / "demo"

app = FastAPI(title="Courier Memory", version="0.1.0",
              description="Uygulama verisi · 1 aylık geçmiş. Orkestratör, Atama, Hafıza, Hasat, Brifing, Değerlendirme ve Bölge ajanları.")


_SV_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _sv_cached() -> Services:
    s = Services.create(os.environ.get("CM_RUN_DIR"))
    s.book.ensure(s.run.meta["critical"]["day"])
    return s


def sv() -> Services:
    """Servisler bir kez kurulur; ilk anda gelen eşzamanlı istekler kilitle beklenir."""
    with _SV_LOCK:
        return _sv_cached()


sv.cache_clear = _sv_cached.cache_clear  # testler için


def _day_ok(day: int) -> int:
    if day not in sv().run.eval_days:
        raise HTTPException(404, f"Gün {day} değerlendirme döneminde değil ({sv().run.eval_days[0]}–{sv().run.eval_days[-1]})")
    return day


# ------------------------------------------------------------------ statik veri
@app.get("/api/status")
def status():
    s = sv()
    return {"mode": s.llm.mode, "model": s.llm.model, "region": s.llm.region, "run_id": s.run.run_id, "app_data": True,
            "cassettes": s.llm.cassette_count(), "memory_seed_day": s.book.seed_day,
            "models": {"assignment": s.assignment.llm.model, "memory": s.memory.llm.model, "briefing": s.briefing.llm.model,
                         "orchestrator": s.orchestrator.llm.model, "harvest": s.harvest.agent.llm.model}}


@app.get("/api/meta")
def meta():
    return sv().run.meta


@app.get("/api/summary")
def summary():
    r = sv().run
    sweep = None
    p = r.dir / "sweep.json"
    if p.exists():
        sweep = json.loads(p.read_text(encoding="utf-8"))
    long = None
    ud = r.dir / "long_term"
    if (ud / "summary.json").exists():
        long = {"summary": json.loads((ud / "summary.json").read_text(encoding="utf-8")),
                "daily": json.loads((ud / "daily.json").read_text(encoding="utf-8"))["arms"],
                "learning_curve": json.loads((ud / "learning_curve.json").read_text(encoding="utf-8"))["arms"],
                "meta": json.loads((ud / "meta.json").read_text(encoding="utf-8"))}
    calib = None
    if (r.dir / "calibration.json").exists():   # hedef değerler şirket içi toplu özettir; arayüze gönderilmez
        calib = json.loads((r.dir / "calibration.json").read_text(encoding="utf-8"))
        calib["rows"] = [{k: v for k, v in row.items() if k != "target"} for row in calib["rows"]]
    extra = {n: json.loads((r.dir / f"{n}.json").read_text(encoding="utf-8")) if (r.dir / f"{n}.json").exists() else None
          for n in ("learning", "ablation", "time")}
    lc = r.file("learning_curve.json")
    return {"summary": r.file("summary.json"), "daily": r.file("daily.json")["arms"],
            "learning_curve": lc["arms"], "learning_same_route": lc.get("same_route"), "recovery": r.file("recovery.json"), "sweep": sweep,
            "long_term": long, "calibration": calib, **extra}


@app.get("/api/learning")
def learning():
    """Hedef 1: çok seed'li işe alım deneyi (cm_sim.learning). Hafızalı ↔ hafızasız öğrenme eğrisi, ustalaşma günü, ilk hafta."""
    p = sv().run.dir / "learning.json"
    if not p.exists():
        raise HTTPException(404, "learning.json yok: python -m cm_sim.learning && python -m cm_sim.publish")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/economics")
def economics(usd_try: float | None = Query(None, gt=0, le=1000), courier_daily_cost_tl: float | None = Query(None, gt=0, le=100000),
            km_cost_tl: float | None = Query(None, ge=0, le=1000), fails_other_tl: float | None = Query(None, ge=0, le=10000),
            second_attempt_min: float | None = Query(None, ge=0, le=240), daily_assignment_question: float | None = Query(None, ge=0, le=100),
            model_assignment: str | None = None, model_memory: str | None = None, model_briefing: str | None = None,
            cache: bool | None = None, scenario: str | None = None):
    """Token maliyeti ↔ kazanç. Parametreler economics.yaml parametrelerini ezer (arayüz kaydırıcıları)."""
    from agents.economics import compute, load_assumptions, load_tokens

    ov = {k: v for k, v in locals().items() if v is not None}
    try:
        a = load_assumptions(ov)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    r = sv().run
    res = compute(r, load_tokens(r), a)
    res["models"] = [{"id": k, "name": v["name"]} for k, v in a["llm"]["models"].items()]
    return res


@app.get("/api/blocks")
def blocks():
    return sv().run.file("blocks.json")


@app.get("/api/couriers")
def couriers():
    return sv().run.file("couriers.json")


@app.get("/api/day/{arm}/{day}")
def day(arm: str, day: int):
    if arm not in ("A", "B", "C", "D"):
        raise HTTPException(404, "Kol A, B, C ya da D olmalı")
    return sv().run.snapshot(arm, _day_ok(day))


# ------------------------------------------------------------------ Atama Ajanı
class DayRequest(BaseModel):
    day: int


class QuestionRequest(BaseModel):
    day: int
    question: str
    history: list[dict] = []
    current: list[dict] | None = None


class ApprovalRequest(BaseModel):
    day: int
    assignment: list[dict]


_APPROVALS: dict[int, list[dict]] = {}


@app.post("/api/assignment/propose")
def propose_assignment(req: DayRequest):
    return sv().assignment.propose(_day_ok(req.day))


@app.post("/api/assignment/ask")
def ask_assignment(req: QuestionRequest):
    if not req.question.strip():
        raise HTTPException(400, "Soru boş olamaz")
    return sv().assignment.ask(_day_ok(req.day), req.question, req.history, req.current or _APPROVALS.get(req.day))


@app.post("/api/assignment/approve")
def approve_assignment(req: ApprovalRequest):
    _APPROVALS[_day_ok(req.day)] = req.assignment
    return {"ok": True}


# ------------------------------------------------------------------ Orkestratör (günün ajanı + insan onayı)
class DecisionRequest(BaseModel):
    decision: str                                   # onay | ret | duzenle
    assignment: list[dict] | None = None              # duzenle: [{kume, kurye}]
    note_: str | None = Field(None, alias="note")


class OrchStartRequest(BaseModel):
    day: int
    manager_review: bool = False                      # müdür acil durum bildirdi: plan temassız kesinleşmez, onaya gelir


class OrchQuestionRequest(BaseModel):
    question: str
    history: list[dict] = []


def _sse(event: str, data: dict, eid: int | None = None) -> str:
    head = f"id: {eid}\n" if eid is not None else ""
    return head + f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _session(kid: str):
    try:
        return sv().sessions.get(kid)
    except KeyError:
        raise HTTPException(404, f"Koşu bulunamadı: {kid}") from None


@app.post("/api/orchestrator/start")
def start_orch(req: OrchStartRequest):
    """Koşuyu arka planda başlatır; iz /kosu/{id} (poll) ya da /kosu/{id}/akis (SSE) ile izlenir. Acil durum yoksa plan
    temassız kesinleşir (status finalized); varsa ya da manager_review ile müdüre eskale edilir (awaiting_approval)."""
    return sv().sessions.start(_day_ok(req.day), background=True, manager_review=req.manager_review).summary()


@app.post("/api/orchestrator/plan")
def plan_orch(req: OrchStartRequest):
    """Eşzamanlı: koşu bitene kadar bekler, tüm izi ve öneriyi döndürür."""
    return sv().sessions.start(_day_ok(req.day), background=False, manager_review=req.manager_review).summary()


@app.get("/api/orchestrator/session/{kid}")
def orch_session(kid: str, after: int = Query(0, ge=0)):
    return _session(kid).summary(after)


@app.get("/api/orchestrator/session/{kid}/stream")
def orch_stream(kid: str, after: int = Query(0, ge=0), tempo_ms: int = Query(0, ge=0, le=5000)):
    """Server-Sent Events: her iz olayı `event: <type>` + `data: <json>`. Planlama evresi bitince `event: last`."""
    k = _session(kid)

    def gen():
        n = after
        while True:
            evs = k.trace.since(n)
            for e in evs:
                yield _sse(e["type"], e, e["i"])
                n = e["i"] + 1
                if tempo_ms:
                    time.sleep(tempo_ms / 1000)
            if k.done.is_set() and n >= len(k.trace):
                yield _sse("last", {"status": k.status, "total_event": n})
                return
            time.sleep(0.05)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/orchestrator/session/{kid}/decision")
def orch_decision(kid: str, req: DecisionRequest):
    _session(kid)
    try:
        return sv().sessions.decision(kid, req.decision, req.assignment, req.note_)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/orchestrator/session/{kid}/ask")
def ask_orch(kid: str, req: OrchQuestionRequest):
    if not req.question.strip():
        raise HTTPException(400, "Soru boş olamaz")
    _session(kid)
    try:
        return sv().sessions.ask(kid, req.question.strip()[:300], req.history)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/plan/{day}")
def plan(day: int):
    p = sv().sessions.plans.get(_day_ok(day))
    if p is None:
        raise HTTPException(404, f"Gün {day} için kesinleşmiş plan yok")
    return p


@app.get("/api/orchestrator/candidates/{day}")
def orch_candidates(day: int):
    """'Kim gitsin': kapasite açığı kadar komşu şube adayı, sıralama ve gerekçe (araç çıktısı; LLM yok)."""
    from agents.orchestrator import DayTools

    s = sv()
    ar = DayTools(s.run, s.book, _day_ok(day))
    k = ar.capacity_gap({})
    return {"capacity": k, "candidates": ar.neighbor_candidates({"need": k["shortfall"], "exclude": [], "current_borrowed": []})}


@app.get("/api/route/{day}/{courier}")
def route(day: int, courier: str):
    """Hedef 3: kuryenin bugünkü rotası, hafızasız ↔ hafızalı karşılaştırma, hafızanın yaptığı değişiklikler (canlı hafızayla)."""
    from agents.orchestrator import DayTools

    s = sv()
    _day_ok(day)
    s.book.ensure(day)
    plan = s.sessions.plans.get(day)
    row = next((x for x in (plan or {}).get("assignment", []) if x["courier"] == courier), None)
    if row is not None:
        cluster, source = int(row["cluster"]), "approved_plan"
    else:
        r = s.run.route_of(day, courier)
        if r is None:
            raise HTTPException(404, f"{courier} gün {day} planda yok")
        cluster, source = int(r["route"]), "simulation_plan"
    ar = DayTools(s.run, s.book, day)
    if courier not in ar.cid:
        raise HTTPException(404, f"{courier} gün {day} müsait değil")
    out = ar.compute_route({"cluster_id": cluster, "courier_id": courier})
    out["plan_source"] = source
    return out


# ------------------------------------------------------------------ Hasat (kıdemliye hedefli soru, teslim olaylarından hipotez)
class HarvestAnswer(BaseModel):
    question_id: str
    text: str | None = None


@app.post("/api/harvest/plan")
def plan_harvest(req: DayRequest):
    return sv().harvest.plan(_day_ok(req.day))


@app.get("/api/harvest/{day}")
def harvest_list(day: int):
    try:
        return sv().harvest.items(_day_ok(day))
    except KeyError:
        raise HTTPException(404, f"Gün {day} için hasat planı yok (POST /api/harvest/plan)") from None


@app.post("/api/harvest/answer")
def harvest_answer(req: HarvestAnswer):
    if not (req.text or "").strip():
        raise HTTPException(400, "Cevap boş olamaz")
    try:
        return sv().harvest.reply(req.question_id, req.text.strip()[:500])
    except KeyError:
        raise HTTPException(404, f"Soru bulunamadı: {req.question_id}") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/api/harvest/simulate-answer")
def simulate_harvest(req: HarvestAnswer):
    """Demo: kıdemli kuryenin cevabını simülasyonun gizli gerçeğinden üretir (simüle edilen insan; `simulate: true`)."""
    try:
        return sv().harvest.simulate_answer(req.question_id)
    except KeyError:
        raise HTTPException(404, f"Soru bulunamadı: {req.question_id}") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


# ------------------------------------------------------------------ Brifing ve Hafıza
@app.get("/api/briefing/{day}/{courier}")
def briefing(day: int, courier: str):
    try:
        return sv().briefing.prepare(_day_ok(day), courier)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


class NoteRequest(BaseModel):
    day: int
    courier: str
    text: str
    lat: float | None = None
    lng: float | None = None
    barcode: str | None = None
    minute: int | None = None


@app.post("/api/note")
def process_note(req: NoteRequest):
    if not req.text.strip():
        raise HTTPException(400, "Not boş olamaz")
    if req.courier not in sv().run.couriers:
        raise HTTPException(404, f"Bilinmeyen kurye: {req.courier}")
    s = sv()
    r = s.memory.process(_day_ok(req.day), req.courier, req.text.strip()[:500], req.lat, req.lng, req.barcode, req.minute)
    _note_to_feed(s, req.day, req.courier, r)
    return r


NOTE_FEED_TYPE = {"saved": "record_added", "updated": "record_strengthened"}


def _note_to_feed(s, day: int, courier: str, r: dict) -> None:
    """Hafıza Ajanı'nın sonucu ajan akışına (not metninin kendisi değil; ayıklanmış sonuç)."""
    addr = r.get("address") or {}
    label = addr.get("label")
    summary = {"saved": f"{label}: yeni kayıt ({r.get('type')}) “{r.get('hint')}”",
               "updated": f"{label}: kayıt güçlendi ({r.get('type')}) “{r.get('hint')}”",
               "noise": "Adresle ilgisiz not; kaydedilmedi", "uncertain": "Adres belirsiz; kuryeye soruldu",
               "rejected": f"Kayıt reddedildi: {r.get('summary')}"}.get(r.get("status"), r.get("summary") or "")
    if r.get("personal_data_redacted"):
        summary += " · kişisel veri/şifre ayıklandı"
    s.feed.add(agent="memory", kind=NOTE_FEED_TYPE.get(r.get("status"), "note"), day=day,
               status="applied" if r.get("status") in NOTE_FEED_TYPE else "info", summary=summary,
               courier=s.run.courier_name(courier), record=(r.get("record") or {}).get("id"), address=addr.get("id"),
               position=[addr.get("lat"), addr.get("lng")] if addr else None, memory_kind=r.get("type"), source=r.get("mode"))


@app.get("/api/memory")
def memory(day: int, address: int | None = None):
    s = sv()
    s.book.ensure(day)
    if address is not None:
        return {"entries": s.book.for_address(address, day)}
    return {"entries": [e for e in s.book.entries if e.get("status", "active") == "active"]}


@app.get("/api/memory/summary")
def memory_summary(day: int):
    s = sv()
    s.book.ensure(day)
    return s.book.summary(day)


class Feedback(BaseModel):
    day: int
    record: str
    valid: bool


@app.post("/api/memory/feedback")
def feedback(req: Feedback):
    s = sv()
    e = s.book.feedback(req.record, req.valid, req.day)
    if e is not None:
        s.feed.add(agent="memory", kind="record_strengthened" if req.valid else "record_dropped", day=req.day, status="applied",
                   summary=f"Kapıda kurye geri bildirimi: “{e['text']}” {'hâlâ geçerli (teyit)' if req.valid else 'değişmiş, kayıt düşürüldü'}",
                   record=e["id"], address=e["address"])
    return {"ok": e is not None, "record": e}


# ------------------------------------------------------------------ durak bilgi kartları ve yaklaşma tetiği
def _stop_cards(day: int, courier: str):
    from agents.cards import StopCards

    s = sv()
    if courier not in s.run.couriers:
        raise HTTPException(404, f"Bilinmeyen kurye: {courier}")
    try:
        return StopCards(s.run, s.book, _day_ok(day), courier, s.sessions.plans.get(day))
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/cards/{day}/{courier}")
def stop_cards(day: int, courier: str, all: bool = False):
    """Kuryenin bugünkü rotasında (hafızalı sıra) durak bilgi kartları; `all=true` kartsız durakları da döndürür."""
    return _stop_cards(day, courier).items(all)


class ApproachRequest(BaseModel):
    day: int
    courier: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    next_order: int | None = None
    shown: list[str] = Field(default_factory=list, max_length=500)


@app.post("/api/approach")
def approach(req: ApproachRequest):
    """Konuma göre şimdi söylenecek kartlar (durumsuz; istemci söylenenleri `shown` ile geri gönderir)."""
    sc = _stop_cards(req.day, req.courier)
    try:
        return sc.approach(req.lat, req.lng, req.next_order, req.shown)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------ Değerlendirme Ajanı (öz-iyileştirme) ve ajan akışı
class ReviewDecisionRequest(BaseModel):
    day: int
    n: int
    decision: str


@app.post("/api/review/run")
def run_review(req: DayRequest):
    """Sabah değerlendirmesi: son günler ↔ önceki günler; düzeltmeler (otomatik, geri alınabilir) ve öneriler (müdür onayı)."""
    return sv().review.morning_review(_day_ok(req.day))


@app.get("/api/review")
def review_state():
    r = sv().review
    return {"last_report": r.last_report, "params": r.params, "question_queue": r.question_queue[-50:]}


@app.post("/api/review/decision")
def review_decision(req: ReviewDecisionRequest):
    """Müdür kararı: approve | reject (önerilerde), undo (uygulanmış otomatik eylemde)."""
    try:
        return sv().review.decision(req.n, req.decision, req.day)
    except KeyError:
        raise HTTPException(404, f"Akış öğesi yok: {req.n}") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/feed")
def agent_feed(after: int = 0, agent: str | None = None, status: str | None = None):
    return {"events": sv().feed.items(after, agent, status)}


@app.post("/api/feed/reset")
def reset_feed():
    sv().feed.reset()
    return {"ok": True}


# ------------------------------------------------------------------ Bölge Ajanı (durak · küme · şube)
_REGION: dict = {}


def _region_stats(day: int):
    """Blok istatistikleri; hafıza değişince yeniden kurulur."""
    from agents.region import RegionStats

    s = sv()
    key = (id(s.run), day, len(s.book.log))
    if _REGION.get("key") != key:
        _REGION.update(key=key, stats=RegionStats(s.run, s.book, day))
    return _REGION["stats"]


@app.get("/api/region/branch")
def region_branch(day: int):
    """Şube katmanı (blok zorluk haritası, hafıza boşlukları) + Bölge Ajanı'nın son raporu (varsa)."""
    out = _region_stats(_day_ok(day)).branch_layer()
    r = sv().region.last_branch
    if r:
        out["agent_report"] = {k: r[k] for k in ("manager_summary", "priority", "questions", "mode", "degraded", "trace")}
    return out


@app.post("/api/region/run")
def run_region(req: DayRequest):
    """Bölge Ajanı · şube görevi: zor blokları yorumlar, hafıza boşluklarına kıdemliye soru açar, müdüre rapor sunar."""
    r = sv().region.branch(_day_ok(req.day))
    return {k: r[k] for k in ("manager_summary", "priority", "questions", "mode", "degraded", "trace", "summary")}


# ------------------------------------------------------------------ Gerçek gün (Beykoz 5 Mayıs): kapsam, küme, kurye aktarımı
REAL_DAY_DIR = ROOT / "data" / "real_day"
_REAL_DAY: dict = {}
_CLUSTER_CARD: dict = {}


def _real_day_file(day: str) -> Path:
    if len(day) != 10 or not all(ch.isdigit() or ch == "-" for ch in day):
        raise HTTPException(422, "Gün YYYY-AA-GG biçiminde olmalı")
    p = REAL_DAY_DIR / f"{day}.json"
    if not p.exists():
        raise HTTPException(404, f"{day} için gerçek gün verisi yok")
    return p


def _real_day(day: str):
    """Gerçek gün servisi (agents.real_day.RealDay); gün başına bir kez kurulur."""
    from agents.real_day import RealDay

    _real_day_file(day)
    s = sv()
    if day not in _REAL_DAY or _REAL_DAY[day][0] is not s.run:
        _REAL_DAY[day] = (s.run, RealDay(s.run, s.book, day), {})
    return _REAL_DAY[day][1], _REAL_DAY[day][2]


@app.get("/api/real-day/{day}")
def real_day(day: str):
    """Gerçek demo günü: sabit bölge ↔ dinamik kümeler, kuryenin bildiği/bilmediği duraklar, gerçek başarısızlık oranları."""
    return FileResponse(_real_day_file(day), media_type="application/json")


@app.get("/api/real-day/{day}/memory")
def real_day_memory(day: str):
    """Günün duraklarında hafıza kapsamı (1 aylık uygulama geçmişi + bu oturumda eklenenler) ve beklenen başarısız teslim."""
    g, _ = _real_day(day)
    return g.memory_summary()


@app.get("/api/real-day/{day}/cluster/{cid}")
def real_day_cluster(day: str, cid: int):
    """Bir kümenin rotası (kümeleme motorunun sırası), kuryenin bilmediği duraklar, kartlar ve Bölge Ajanı'nın küme kartı."""
    g, _ = _real_day(day)
    try:
        k = g.cluster(cid)
    except KeyError:
        raise HTTPException(404, f"Küme {cid} yok") from None
    d = k["stops"]
    s = sv()
    key = (day, cid, len(s.book.log))                                   # canlıda her istekte LLM çağrılmasın
    if _CLUSTER_CARD.get(key) is None:
        _CLUSTER_CARD.clear()
        _CLUSTER_CARD[key] = s.region.cluster_card(g.day, [(x["lat"], x["lng"]) for x in d], [x["unfamiliar"] for x in d], k["name"],
                                                   [[c["type"] for c in x["cards"]] for x in d])
    k["cluster_card"] = _CLUSTER_CARD[key]
    return k


@app.get("/api/real-day/{day}/transfer")
def real_day_transfer(day: str):
    """Kurye aktarımı: komşu şube yoğun → Beykoz bir kurye verir → yeniden dengeleme (yaklaşık) → bilgi kaybı + hafıza."""
    g, cache = _real_day(day)
    key = len(sv().book.log)
    if cache.get("key") != key:
        cache.update(key=key, result=g.transfer())
    return cache["result"]


@app.post("/api/demo/reset")
def reset_demo(req: DayRequest):
    """Sunum öncesi: hafıza, ajan akışı, Değerlendirme Ajanı parametreleri ve önbellekler baştan."""
    from agents.delivery_time import time_source

    s = sv()
    time_source(s.run).reset()
    n = s.book.reset(_day_ok(req.day))
    s.feed.reset()
    s.review.params.update(unfamiliar_stop_extra_min=0.0, general_bias_min=0.0)
    s.review.question_queue.clear()
    s.review.last_report = None
    s.region.asked_blocks.clear()
    s.region.last_branch = None
    _CLUSTER_CARD.clear()
    _REAL_DAY.clear()
    _REGION.clear()
    return {"ok": True, "memory_records": n}


@app.post("/api/memory/reset")
def reset_memory(req: DayRequest):
    from agents.delivery_time import time_source

    s = sv()
    time_source(s.run).reset()          # saat teyitleri ve Orkestratör'ün zaman seçimi de sıfırlanır
    return {"ok": True, "total": s.book.reset(_day_ok(req.day))}


# ------------------------------------------------------------------ Teslim zamanı analizi (kayıtlardan, notsuz)
# ------------------------------------------------------------------ sabah (ayrıştırma indirme okutmasında)
class ScanRequest(BaseModel):
    day: int
    shipment: str


def _morning_tools(day: int):
    from agents.orchestrator import DayTools

    s = sv()
    _day_ok(day)
    ar = DayTools(s.run, s.book, day)
    plan = s.sessions.plans.get(day)
    if plan:                                    # onaylı planın atamasıyla raf → kurye
        ar._mapping = {int(x["cluster"]): x["courier"] for x in plan["assignment"]}
    return s, ar, ("approved_plan" if plan else "simulation_plan")


def _shipment_ids(snap: dict, day: int) -> list[str]:
    """Uygulamanın ürettiği gönderi kimlikleri (barkod değil): G<gün>-<adres>-<sıra>; araçtaki sıra deterministik karışık."""
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    ids = [f"G{day}-{int(st[F['address']])}-{j + 1}" for r in snap["routes"] for st in r["stops"] for j in range(int(st[F["n"]]))]
    np.random.default_rng(day).shuffle(ids)
    return ids


@app.get("/api/morning/{day}")
def morning(day: int):
    """İndirme okutmasında ayrıştırma planı (raflar, yükleme sırası, tahmini çıkış), günün çıkışları (kol D gerçekleşen ↔
    aynı rota bugünkü sabahla) ve simülasyonun sabah ölçümü (summary.sabah)."""
    s, ar, source = _morning_tools(day)
    p = ar.sorting_plan({})
    snap = s.run.snapshot("D", day)
    departs = []
    for r in snap["routes"]:
        cf = (r.get("counterfactual") or {}).get("current_morning") or {}
        departs.append({"cluster": int(r["route"]), "courier": r["courier"], "name": r["courier_name"], "departure": r.get("departure"),
                    "return_time": round(float(r.get("departure") or 0) + float(r["minutes"]), 1) if r.get("departure") is not None else None,
                    "departure_current": cf.get("start"), "return_current": cf.get("end")})
    return {"day": day, "plan_source": source, "plan": p, "departures": departs, "summary": s.run.file("summary.json").get("morning"),
            "example_shipments": _shipment_ids(snap, day)[:40]}


@app.post("/api/morning/scan")
def morning_scan(req: ScanRequest):
    """İndirme okutması: gönderi → kurye · raf · yükleme sırası (son durak önce yüklenir). Planda yoksa 'esnek' raf (istisna)."""
    s, ar, source = _morning_tools(req.day)
    p = ar.sorting_plan({})
    snap = s.run.snapshot("D", req.day)
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    parts = req.shipment.strip().split("-")
    address = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else None
    shelf_of = {x["cluster"]: x for x in p["shelves"]}
    for r in snap["routes"]:
        st = r["stops"]
        for i, x in enumerate(st):
            if address is not None and int(x[F["address"]]) == address:
                shelf = shelf_of.get(int(r["route"]))
                yk = len(st) - i
                return {"shipment": req.shipment, "exception": False, "shelf": shelf["shelf"], "cluster": shelf["cluster"], "courier": shelf["courier"],
                        "name": shelf["name"], "stop_order": i + 1, "load_order": yk, "stop": len(st),
                        "label": s.run.addr_label[address], "plan_source": source,
                        "instruction": f"Raf {shelf['shelf']} · {shelf['name']} · yükleme {yk}/{len(st)}"}
        for d in ((r.get("plan") or {}).get("deferred") or []):
            if address is not None and int(d["address"]) == address:
                return {"shipment": req.shipment, "exception": True, "shelf": "next_day", "label": s.run.addr_label[address],
                        "instruction": "Ertesi gün rafı · adres bugün kapalı (hafızada iki kaynakla teyitli)", "plan_source": source}
    return {"shipment": req.shipment, "exception": True, "shelf": "flexible", "plan_source": source,
            "instruction": "Esnek raf · planda yok ya da adres çözülemedi; müdür ekranına düştü"}


@app.get("/api/time/example")
def time_example():
    """Demo: bir adresin geçmişi (saat → sonuç), ajanın bulgusu, rotadaki değişiklik ve o duraktaki sonuç (simülasyon)."""
    from agents.orchestrator import DayTools
    from agents.delivery_time import time_source

    s = sv()
    ex = s.run.meta.get("time_example")
    if not ex:
        raise HTTPException(404, "Bu çalıştırmada zaman örneği yok (zaman analizi kapalı ya da taşınan durak yok)")
    day, a, courier = int(ex["day"]), int(ex["address"]), ex["courier"]
    zk = time_source(s.run)
    b = zk.data.findings(day, [a]).get(a)
    ar = DayTools(s.run, s.book, day)
    route = ar.compute_route({"cluster_id": int(ex["cluster"]), "courier_id": courier}) if courier in ar.cid else None
    ch = next((c for c in (route or {}).get("changes", []) if c.get("type") == "time" and c["address"] == a), None)
    tr = s.run.file("truth.json").get("presence") or {}
    return {"app_data": True, "example": ex,
            "agent": {"finding": zk.row(a, b, day) if b else None, "table": zk.data.address_table(a, day),
                     "history": zk.data.history(a, day)},
            "route": {"change": ch, "same_as_sim": (route or {}).get("same_as_sim"),
                     "diff": ((route or {}).get("comparison") or {}).get("diff")},
            "hidden_truth": {"profile": tr["profiles"][tr["profile"][a]] if tr else None,
                             "note": "Yalnız değerlendirme için (simülasyonun gizli gerçeği); ajan bunu görmez."},
            "summary": s.run.file("summary.json").get("time_analysis"),
            # kural "rota uzamaz, fazla mesai yok"; ikinci örnek = kısıt yüzünden kaydırılamayan bulgu ve alternatifi
            "constraint": (s.run.file("summary.json").get("time_analysis") or {}).get("constraint"),
            "example_constraint": s.run.meta.get("time_example_constraint")}


@app.get("/api/time/{day}/alternatives")
def time_alternatives(day: int):
    """Kısıt (rota uzamaz, bant aşılmaz, vardiya sonrasına kaydırma yok) yüzünden aynı rotada kaydırılamayan bulgular ve
    ajanın sırayla alternatifleri (başka kuryeye aktarma → ertesi gün / akşam-teslim noktası; hepsinde SMS önerisi). Müdür kararı."""
    from agents.orchestrator import DayTools

    s = sv()
    ar = DayTools(s.run, s.book, _day_ok(day))
    return ar.time_alternatives({})


@app.get("/api/time/{day}")
def time_day(day: int, min_confidence: str = Query("low", pattern="^(low|mid|high)$")):
    """Günün planındaki duraklarda teslim zamanı bulguları (yalnız önceki günlerin kaydından) ve rotaya alınan seçim."""
    from agents.orchestrator import DayTools

    s = sv()
    ar = DayTools(s.run, s.book, _day_ok(day))
    out = ar.delivery_time_analysis({"min_confidence": min_confidence})
    out["selection"] = ar.time_summary()
    return out


@app.get("/api/time/{day}/address/{address}")
def time_address(day: int, address: int):
    """Tek adres: geçmiş denemeler (saat → sonuç), dilim tablosu (büzülmüş tahmin), bulgu ve teyit durumu."""
    from agents.delivery_time import time_source

    s = sv()
    _day_ok(day)
    if not (0 <= address < len(s.run.addr_kind)):
        raise HTTPException(404, f"Adres yok: {address}")
    zk = time_source(s.run)
    b = zk.data.findings(day, [address]).get(address)
    return {"address": s.run.address(address), "day": day, "history": zk.data.history(address, day), "table": zk.data.address_table(address, day),
            "finding": zk.row(address, b, day) if b else None, "confirmation": zk._confirmation(address, day)}


# ------------------------------------------------------------------ ses (P1: Amazon Polly)
@app.get("/api/speech")
def speech(text: str = Query(..., min_length=1, max_length=600)):  # Polly sınırı 3000 faturalı karakter; arayüz 600'de keser
    if os.environ.get("CM_POLLY", "0") != "1" or sv().llm.mode == "mock":
        return JSONResponse({"detail": "Polly kapalı; tarayıcı sesi kullanılır."}, status_code=501)
    # tr-TR: Burcu yalnız neural, Filiz yalnız standard motorla çalışır (Polly ses listesi)
    voice = os.environ.get("CM_POLLY_VOICE") or "Burcu"
    engine = os.environ.get("CM_POLLY_ENGINE") or ("standard" if voice == "Filiz" else "neural")
    try:
        import boto3

        polly = boto3.client("polly", region_name=sv().llm.region)
        out = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice, Engine=engine, LanguageCode="tr-TR")
        return Response(out["AudioStream"].read(), media_type="audio/mpeg")
    except Exception as e:  # sesi alamazsak arayüz tarayıcı sesine düşer
        return JSONResponse({"detail": f"Polly hatası: {e}"}, status_code=501)


# ------------------------------------------------------------------ sesli not (P1: Amazon Transcribe, tr-TR)
@app.get("/api/transcribe")
def transcribe_status():
    """Sunucu ses tanıması açık mı? Kapalıysa 501: arayüz tarayıcı tanımasını kullanır."""
    return transcribe.status()


@app.post("/api/transcribe")
async def transcribe_audio(request: Request):
    """Ham ses gövdesi (audio/pcm;rate=16000 · audio/ogg · audio/flac, en fazla 60 sn) → {"text", "language"}."""
    return await transcribe.handle(request)


# ------------------------------------------------------------------ canlı akış (sunum ekranı başlatır, QR izleyicileri izler)
@app.get("/api/live")
async def live_state(after: int = Query(0, ge=0)):
    """Canlı akışın durumu ve `after`'dan sonraki olayları (SSE açılamazsa poll)."""
    return LIVE.snapshot(after)


@app.post("/api/live/start")
async def live_start(chain: str = Query("day", pattern="^(day|agentcore)$")):
    """Zinciri sunucuda bir kez başlatır; koşu sürerken ikinci başlatma 409 (hangi zincir olursa olsun).
    `chain=day`: sekiz adım, süreç içi ajanlar · `chain=agentcore`: altı istek AgentCore Supervisor'dan (kapalıysa 501)."""
    if chain == "agentcore" and not agentcore_chain.enabled():
        raise HTTPException(501, "AgentCore zinciri bu sunucuda kapalı (CM_AGENTCORE_CHAIN=0)")
    try:
        if chain == "agentcore":
            return LIVE.start(target=LIVE.runner(agentcore_chain.Chain), kind="agentcore")
        return LIVE.start()
    except LiveBusy:
        raise HTTPException(409, "Canlı akış zaten çalışıyor") from None


def _live_ctx() -> dict:
    s = sv()
    c = s.run.meta["critical"]
    return {"day": c["day"], "courier": c["courier"], "name": c.get("courier_name", ""), "mode": s.llm.mode,
            "agentcore": agentcore_chain.enabled()}


@app.get("/api/live/stream")
async def live_stream(request: Request):
    """SSE: önce `hello` {status, run_id}, sonra geçerli koşunun bütün olayları ve yenileri. `id: <koşu>:<sıra>`;
    yeniden bağlanan tarayıcı Last-Event-ID ile kaldığı yerden sürer. 15 sn'de bir yorum satırı (CloudFront ve ALB bağlantıyı kesmesin).
    async: izleyici başına iş parçacığı tutulmaz."""
    run, n = None, 0
    last = request.headers.get("last-event-id", "")
    if ":" in last:
        try:
            r, i = last.split(":", 1)
            run, n = int(r), int(i) + 1
        except ValueError:
            run, n = None, 0

    try:
        ctx = await asyncio.to_thread(_live_ctx)
    except Exception:
        ctx = None

    async def gen():
        nonlocal run, n
        snap = LIVE.snapshot(10**9)
        yield "retry: 2000\n\n" + _sse("hello", {"status": snap["status"], "run_id": snap["run_id"], "kind": snap["kind"],
                                                 "ctx": ctx})
        beat = time.monotonic()
        while True:
            evs, run, n, _ = LIVE.pull(run, n)
            for e in evs:
                yield _sse(e["t"], e, f"{e['run']}:{e['n']}")
            now = time.monotonic()
            if evs:
                beat = now
            elif now - beat > 15:
                beat = now
                yield ": ping\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ arayüz
# Sondaki "/" olmadan gelen istek göreli yönlendirilir. Starlette'in kendi yönlendirmesi mutlak adres kurar: CloudFront
# arkasında Host ALB'nin adı, şema http olur (https://…/flow → http://…elb.amazonaws.com/flow/). Göreli adres tarayıcıda
# aynı kökte (HTTPS) kalır ve ters vekil öneki (/proxy/<port>/) altında da çalışır.
def _slash(name: str):
    def go():                       # parametresiz: sorgudan hedef alınmaz (açık yönlendirme olmaz)
        return RedirectResponse(f"{name}/")
    return go


for _name in ("story", "flow", "demo"):
    app.add_api_route(f"/{_name}", _slash(_name), methods=["GET", "HEAD"], include_in_schema=False)

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
if UI_STORY.exists():  # hikaye arayüzü (sunum): /story/
    app.mount("/story", StaticFiles(directory=UI_STORY, html=True), name="story")
if UI_FLOW.exists():  # nasıl çalışır: ajanların izi, API çağrıları ve veri akışı adım adım: /flow/
    app.mount("/flow", StaticFiles(directory=UI_FLOW, html=True), name="flow")
if UI_DEMO.exists():  # demo izi (QR): geçmiş demo koşusunda her ajanın aldığı, düşündüğü, verdiği: /demo/
    app.mount("/demo", StaticFiles(directory=UI_DEMO, html=True), name="demo")


@app.get("/")
def index():
    """Demo arayüzü: hikaye (8 sahne). Eski tek sayfa ayrıntı ekranları /legacy adresinde kalır."""
    if (UI_STORY / "index.html").exists():
        return RedirectResponse("story/")          # göreli: ters vekil öneki (/proxy/<port>/) altında da çalışır
    return legacy()


@app.get("/legacy")
def legacy():
    """Eski tek sayfa arayüzü."""
    p = UI_LEGACY / "index.html"
    if not p.exists():
        return JSONResponse({"detail": "Arayüz henüz yok (ui/legacy/index.html)."}, status_code=404)
    return FileResponse(p)

