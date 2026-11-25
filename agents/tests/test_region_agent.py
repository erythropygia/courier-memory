"""Bölge Ajanı (küme kartı, şube raporu) ve Değerlendirme Ajanı: kurallı yedek ve canlı döngü (sahte LLM, ağsız)."""
import pytest

from agents import Services
from agents.region import RegionStats
from agents.region_agent import QUESTION_MAX
from agents.tests.test_agents import FakeLLM


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    s.book.reset(s.run.meta["critical"]["day"])
    return s


def _cluster(sv, day):
    snap = sv.run.snapshot("D", day)
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    r = snap["routes"][0]
    return [(x[F["lat"]], x[F["lng"]]) for x in r["stops"]], [bool(x[F["unfamiliar"]]) for x in r["stops"]], r["courier_name"]


def _tool(i, name, inp):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": str(i), "name": name, "input": inp}]}


def test_branch_rule_path_opens_questions_once(sv):
    day = sv.run.meta["critical"]["day"]
    r = sv.region.branch(day)
    tools = [e["tool"] for e in r["trace"] if e["type"] == "tool"]
    assert tools[:2] == ["branch_summary", "hard_blocks"] and tools[-1] == "present_branch_report"
    assert r["manager_summary"] and len(r["questions"]) <= 3
    first = {q["block_id"] for q in r["questions"]}
    r2 = sv.region.branch(day)
    assert not first & {q["block_id"] for q in r2["questions"]}                   # aynı blok aynı gün iki kez sorulmaz
    assert len(sv.region.asked_blocks[day]) <= QUESTION_MAX
    assert any(o["type"] == "question" for o in sv.feed.items(agent="region"))


def test_cluster_rule_path(sv):
    day = sv.run.meta["critical"]["day"]
    d, y, name = _cluster(sv, day)
    k = sv.region.cluster_card(day, d, y, name)
    assert k["courier_card"][0].startswith(f"Günaydın {name}") and len(k["courier_card"]) <= 4 and k["mode"] == "mock"
    assert [e["tool"] for e in k["trace"] if e["type"] == "tool"] == ["cluster_summary", "present_cluster_card"]


def test_branch_live_path_fake_llm(sv):
    day = sv.run.meta["critical"]["day"]
    b = RegionStats(sv.run, sv.book, day)
    gap = [x["block_id"] for x in (b.block(h) for h, s in b.st.items() if s["attempt"] >= 3) if x["gap"]]
    target = gap[:2] + ["0_0"]                                              # sonuncusu boşluk değil → araç reddeder
    sv.region.llm = FakeLLM([
        _tool(1, "branch_summary", {}),
        _tool(2, "hard_blocks", {"max_count": 5, "gaps_only": True}),
        _tool(3, "open_question", {"block_ids": target, "rationale": "hafızası boş, 2/14 deneme başarısız"}),
        _tool(4, "present_branch_report", {"summary": ["Bugün 2 boşluk bloğu için soru açıldı."] * 6, "priority_blocks": target[:2]}),
    ])
    r = sv.region.branch(day)
    assert r["mode"] == "live" and not r["degraded"] and len(r["manager_summary"]) == 4          # en çok 4 cümle
    assert {q["block_id"] for q in r["questions"]} == set(gap[:2]) and len(r["priority"]) == 2
    rez = next(e for e in r["trace"] if e["type"] == "result" and e["tool"] == "open_question")["data"]
    assert [x["block_id"] for x in rez["rejected"]] == ["0_0"]
    assert all(e["source"] == "llm" for e in r["trace"] if e["type"] == "tool")


def test_cluster_live_error_falls_back_to_rule(sv):
    day = sv.run.meta["critical"]["day"]
    d, y, name = _cluster(sv, day)
    sv.region.llm = FakeLLM([{"stop_reason": "refusal", "content": []}])
    k = sv.region.cluster_card(day, d, y, name)
    assert k["degraded"] is True and k["courier_card"] and any(e["type"] == "fallback" for e in k["trace"])


def test_review_live_path_fake_llm(sv):
    day = sv.run.meta["critical"]["day"]
    sv.review.llm = FakeLLM([
        _tool(1, "trend", {}),
        _tool(2, "apply", {"actions": [{"type": "parameter", "target": {"name": "unfamiliar_stop_extra_min", "value": 99}, "rationale": "sınama 60 → 41 dk"},
                                          {"type": "proposal", "target": "Atamada tanıdıklık ağırlığını artırın.", "rationale": "3 günde %26 yabancı"}]}),
        _tool(3, "present_report", {"summary": "İyi yönde.", "going_well": ["ilk deneme"], "going_badly": []}),
    ])
    r = sv.review.morning_review(day)
    assert r["mode"] == "live" and not r["degraded"] and r["report"]["summary"] == "İyi yönde."
    assert r["params"]["unfamiliar_stop_extra_min"] == 8.0                                     # korkuluk: sınıra kırpılır
    assert any(o["status"] == "awaiting_approval" for o in sv.feed.items(agent="review"))
