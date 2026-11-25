import pytest

from agents.economics import compute, load_assumptions, load_tokens
from agents.rundata import RunData


def test_economics_structure_and_monotonic():
    run = RunData()
    tok = load_tokens(run)
    base = compute(run, tok, load_assumptions())
    assert base["app_data"] is True and base["llm"]["daily_tl"] > 0
    assert set(base["gain"]) == {"vs_C", "vs_B"}
    assert base["gain"]["vs_B"]["prevented_fails_day"] >= base["gain"]["vs_C"]["prevented_fails_day"]
    hi = compute(run, tok, load_assumptions({"fails_other_tl": 100}))
    assert hi["gain"]["vs_C"]["direct_gain_tl_day"] > base["gain"]["vs_C"]["direct_gain_tl_day"]
    cheap = compute(run, tok, load_assumptions({"model_memory": "anthropic.claude-haiku-5-5"}))
    assert cheap["llm"]["daily_tl"] < base["llm"]["daily_tl"]
    cached = compute(run, tok, load_assumptions({"cache": True}))
    assert cached["llm"]["daily_tl"] <= base["llm"]["daily_tl"]


def test_token_estimate_shape():
    tok = load_tokens(RunData())
    for k in ("propose_assignment", "ask_assignment", "memory", "briefing"):
        assert tok[k]["input"] > 0 and tok[k]["output"] > 0 and tok[k]["request"] >= 2


def test_operations_waterfall_consistent():
    run = RunData()
    e = compute(run, load_tokens(run), load_assumptions())
    sel = e["operation"]["waterfall"]
    assert sel[0]["type"] == "start" and sel[-1]["type"] == "result"
    assert abs(sel[0]["tl_day"] + sum(x["tl_day"] for x in sel[1:-1]) - sel[-1]["tl_day"]) <= 3   # yuvarlama
    m = e["headline"]
    assert m["savings_tl_day"] == e["operation"]["arms"]["A"]["total_tl_day"] - e["operation"]["arms"]["D"]["total_tl_day"]
    assert m["quality"]["fails_per_day_agentless"] > m["quality"]["fails_per_day_memory"]


def test_llm_scenarios():
    run = RunData()
    tok = load_tokens(run)
    t = compute(run, tok, load_assumptions({"scenario": "cautious"}))
    o = compute(run, tok, load_assumptions({"scenario": "optimize"}))
    assert o["llm"]["daily_tl"] < t["llm"]["daily_tl"] / 5
    assert {x["scenario"] for x in t["llm_scenarios"]} == {"cautious", "optimize"}
    morning = t.get("morning") is not None          # Faz 5: yayımlanan çalıştırmada sabah karşı-olgusu varsa ayrı kalem
    assert [x["code"] for x in t["operation"]["waterfall"]] == (["today", "dynamic", "agentless", "assignment", "memory"]
                                                           + (["morning"] if morning else []) + ["result"])
    s = t["operation"]["waterfall"]
    assert sum(x["tl_day"] for x in s[1:-1]) == pytest.approx(s[-1]["tl_day"] - s[0]["tl_day"], abs=len(s))   # şelale kapanır
