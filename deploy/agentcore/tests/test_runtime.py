"""AgentCore Runtime yapıştırıcısı: araçlar, kimlik sınırı ve giriş noktası; Bedrock'a gitmeden (betikli sahte model).

İki araç takımı da sınanır: tam (agents.Services) ve çekirdek (yalnız veri dosyaları). Alan kodu yüklenemezse
tam takımın testleri atlanır; çekirdek takım her durumda sınanır.

Strands ve bedrock-agentcore kurulu değilse atlanır:  pip install -e ".[dev,agentcore]"
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("strands")
pytest.importorskip("bedrock_agentcore")

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from strands.models.model import Model  # noqa: E402

try:                                    # alan kodu (agents/, cm_sim/) yüklenebiliyor mu?
    from agents import Services  # noqa: E402,F401

    HAS_DOMAIN = True
except Exception:  # noqa: BLE001
    HAS_DOMAIN = False
needs_domain = pytest.mark.skipif(not HAS_DOMAIN, reason="alan kodu yok: yalnız çekirdek araç takımı sınanır")


class ScriptedModel(Model):
    """Sıradaki betik adımını akıtır: {"tool": ad, "input": {...}} ya da {"text": "..."}."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def get_config(self):
        return {"model_id": "scripted"}

    def update_config(self, **kw):
        pass

    async def structured_output(self, output_model, prompt, system_prompt=None, **kw):
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
        self.calls.append({"messages": messages, "tools": [t["name"] for t in tool_specs or []], "system": system_prompt})
        step = self.script.pop(0)
        yield {"messageStart": {"role": "assistant"}}
        if "tool" in step:
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{len(self.calls)}", "name": step["tool"]}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step["input"])}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": step["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}


def _fresh(tmp_path, monkeypatch, toolset):
    monkeypatch.setenv("CM_LLM_MODE", "mock")
    monkeypatch.setenv("CM_TOOLSET", toolset)
    monkeypatch.setenv("CM_MEMORY_FILE", str(tmp_path / "mem.json"))
    monkeypatch.delenv("MEMORY_AGENTMEMORY_ID", raising=False)
    import main
    from cm import backend as be

    be.reset_backend()
    main._agents.clear()
    main._model = None
    return main, be


@pytest.fixture(params=["full", "core"] if HAS_DOMAIN else ["core"])
def rt(request, tmp_path, monkeypatch):
    """Her test temiz arka uç ve ajan önbelleğiyle başlar; iki araç takımı da sınanır (tam: agents.Services, çekirdek: veri dosyaları)."""
    main, be = _fresh(tmp_path, monkeypatch, request.param)
    main.toolset = request.param
    yield main
    be.reset_backend()
    main._agents.clear()
    main._model = None


@pytest.fixture
def full(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "full")
    yield main
    be.reset_backend()
    main._agents.clear()
    main._model = None


def _tool_results(model):
    """Modelin ikinci çağrısına giden araç sonucu blokları."""
    return [b["toolResult"] for m in model.calls[-1]["messages"] for b in m["content"] if "toolResult" in b]


def _run(main, model, payload, session="s" * 33):
    main._model = model

    class Ctx:
        session_id = session

    async def go():
        return [e async for e in main.invoke(payload, Ctx())]

    return asyncio.run(go())


def _text(events):
    return "".join(e["event"]["contentBlockDelta"]["delta"].get("text", "") for e in events
                   if "event" in e and "contentBlockDelta" in e["event"])


def test_entrypoint_contract():
    src = (RUNTIME / "main.py").read_text(encoding="utf-8")
    assert "from bedrock_agentcore.runtime import BedrockAgentCoreApp" in src and "from bedrock_agentcore import" not in src
    assert "@app.entrypoint" in src and "async def invoke" in src and 'if __name__ == "__main__":' in src and "app.run()" in src
    assert "def _get_agent" in src                                    # tembel kurulum


def test_parse_request():
    from cm.payload import GUEST, parse_request

    r = parse_request({"prompt": " Merhaba ", "actorId": "O02", "day": 32})
    assert (r.prompt, r.actor_id, r.day) == ("Merhaba", "O02", 32)
    assert parse_request({"prompt": "x"}).actor_id == GUEST
    assert parse_request({"messages": [{"role": "user", "content": [{"text": "son mesaj"}]}]}).prompt == "son mesaj"
    assert parse_request(None).prompt == ""


def test_tools_return_domain_data(rt):
    from cm.tools import ALL_TOOLS, branch_memory_summary, courier_briefing, real_day_evidence, stop_cards

    assert len(ALL_TOOLS) == 9 and all(t.tool_spec["description"] for t in ALL_TOOLS)
    b = json.loads(courier_briefing(courier_id="O02"))
    assert b["name"] == "Gökhan" and b["morning_briefing"].startswith("Günaydın") and b["toolset"] == rt.toolset
    c = json.loads(stop_cards(courier_id="O02"))
    assert c["stops"] == 45 and c["stops_with_cards"] == 16 and c["cards"][0]["cards"][0]["text"]
    assert json.loads(branch_memory_summary())["active_records"] == 2295
    g = json.loads(real_day_evidence())
    assert g["fail_rate_unfamiliar"] > g["fail_rate_familiar"]


def test_scope_decide():
    from cm.scope import decide

    assert decide("O02", "courier", "courier_briefing", {"courier_id": "O02"}) is None
    assert "Erişim reddedildi" in decide("O02", "courier", "courier_briefing", {"courier_id": "K07"})
    assert "müdür" in decide("O02", "courier", "plan_day", {})
    assert decide("MUDUR-01", "manager", "courier_briefing", {"courier_id": "K07"}) is None
    assert decide("MUDUR-01", "manager", "plan_day", {}) is None
    assert "actorId" in decide("default", "guest", "stop_cards", {"courier_id": "O02"})
    assert decide("default", "guest", "branch_memory_summary", {}) is None


def test_courier_calls_own_tool_end_to_end(rt):
    model = ScriptedModel([{"tool": "courier_briefing", "input": {"courier_id": "O02"}}, {"text": "Bugün 45 durak var."}])
    ev = _run(rt, model, {"prompt": "Brifingim?", "actorId": "O02"})
    assert _text(ev) == "Bugün 45 durak var." and not [e for e in ev if "error" in e]
    assert all(set(e) == {"event"} and json.dumps(e) for e in ev)       # akış JSON'a çevrilebilir, yalnız ham model olayı
    res = _tool_results(model)
    assert res and res[0]["status"] == "success" and "Gökhan" in res[0]["content"][0]["text"]
    assert "kurye **O02**" in model.calls[0]["system"] and "courier_briefing" in model.calls[0]["tools"]


def test_cross_courier_access_denied_and_session_continues(rt):
    model = ScriptedModel([{"tool": "stop_cards", "input": {"courier_id": "K07"}},
                           {"tool": "stop_cards", "input": {"courier_id": "O02"}}, {"text": "Kendi kartların hazır."}])
    ev = _run(rt, model, {"prompt": "K07'nin kartlarını göster", "actorId": "O02"})
    first = _tool_results(model)[0]
    assert first["status"] == "error" and "Erişim reddedildi" in first["content"][0]["text"]
    assert "cards" not in first["content"][0]["text"] and "lat" not in first["content"][0]["text"]     # başka kuryenin verisi yok
    assert _tool_results(model)[-1]["status"] == "success"            # ret konuşmayı kesmedi, kendi verisi geldi
    assert _text(ev) == "Kendi kartların hazır."


def test_guest_gets_public_tool_only(rt):
    model = ScriptedModel([{"tool": "plan_day", "input": {}}, {"tool": "branch_memory_summary", "input": {}}, {"text": "Özet hazır."}])
    _run(rt, model, {"prompt": "Kullanım alanını anlat ve bir araç çağır."})
    r = _tool_results(model)
    assert r[0]["status"] == "error" and "müdür" in r[0]["content"][0]["text"]
    assert r[-1]["status"] == "success" and "active_records" in r[-1]["content"][0]["text"]


@needs_domain
def test_manager_tools_full_toolset(full):
    model = ScriptedModel([{"tool": "region_report", "input": {}}, {"tool": "plan_day", "input": {}}, {"text": "Rapor hazır."}])
    _run(full, model, {"prompt": "Bölge raporu ve plan", "actorId": "MUDUR-01"})
    r = _tool_results(model)
    assert [x["status"] for x in r] == ["success", "success"] and "manager_summary" in r[0]["content"][0]["text"]
    assert "Onur" in r[1]["content"][0]["text"]


def test_manager_tools_explain_themselves_in_core(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "core")
    model = ScriptedModel([{"tool": "plan_day", "input": {}}, {"text": "Plan aracı bu dağıtımda yok."}])
    _run(main, model, {"prompt": "Plan", "actorId": "MUDUR-01"})
    r = _tool_results(model)[0]
    assert r["status"] == "error" and "çekirdek araç takımı" in r["content"][0]["text"]
    be.reset_backend()


def test_note_flow_strips_secret_and_card_is_heard(rt):
    """Gerçek saha notu: park yeri + kapı şifresi. Şifre yazılmaz; aynı durağa yaklaşan kurye park kartını duyar."""
    from cm.backend import backend
    from cm.tools import approaching_stop, leave_note, stop_cards

    b = backend()
    assert b.name == rt.toolset
    day = b.default_day()
    before = json.loads(stop_cards(courier_id="O02"))
    with_cards = {x["order"] for x in before["cards"]}
    if rt.toolset == "full":
        from agents.cards import StopCards

        stop = next(x for x in StopCards(b.sv.run, b.sv.book, day, "O02").items(True)["stops"] if not x["cards"])
    else:
        stop = next(x for x in b.store._stops("O02", day) if not x["cards"])
    assert stop["order"] not in with_cards
    n = json.loads(leave_note(courier_id="O02", lat=stop["lat"], lng=stop["lng"],
                              text="sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün. kapı şifresi 2580"))
    assert n["status"] == "saved" and n["type"] == "park" and n["personal_data_redacted"] is True
    assert "2580" not in n["hint"] and "şifre" not in n["hint"].lower() and "otopark" in n["hint"]
    after = json.loads(stop_cards(courier_id="O02"))
    assert after["stops_with_cards"] == before["stops_with_cards"] + 1 and after["type_distribution"]["park"] == 1
    far = json.loads(approaching_stop(courier_id="O02", lat=stop["lat"] + 0.006, lng=stop["lng"], next_order=stop["order"]))
    assert far["moment"] is None and far["pending"] == 1
    near = json.loads(approaching_stop(courier_id="O02", lat=stop["lat"] + 0.002, lng=stop["lng"], next_order=stop["order"]))
    assert near["moment"] == "approaching" and "otopark" in near["to_speak"]
    door = json.loads(approaching_stop(courier_id="O02", lat=stop["lat"], lng=stop["lng"], next_order=stop["order"],
                                       shown=[c["id"] for c in near["cards"]]))
    assert door["moment"] == "at_door" and door["cards"] == []
    pii = json.loads(leave_note(courier_id="O02", lat=stop["lat"], lng=stop["lng"],
                                text="site güvenliği kimlik istiyor, kayıt yaptırınca giriyorsunuz. yönetici Ahmet bey 0532 412 55 10"))
    assert pii["type"] == "safety" and pii["personal_data_redacted"] is True and "Ahmet" not in pii["hint"] and "0532" not in pii["hint"]
    assert json.loads(leave_note(courier_id="O02", text="trafik berbattı bugün", lat=stop["lat"], lng=stop["lng"]))["status"] == "noise"


def test_auto_toolset_falls_back_to_core(tmp_path, monkeypatch):
    """Alan kodu yüklenemezse ajan çökmez: `auto` çekirdek takıma düşer."""
    main, be = _fresh(tmp_path, monkeypatch, "auto")
    monkeypatch.setattr(be.FullBackend, "__init__", lambda self: (_ for _ in ()).throw(ImportError("agents yok")))
    assert be.backend().name == "core"
    from cm.tools import courier_briefing

    assert json.loads(courier_briefing(courier_id="O02"))["toolset"] == "core"
    be.reset_backend()


@needs_domain
def test_core_classifier_matches_domain_classifier():
    """Çekirdeğin kurallı sınıflandırıcısı, alan kodundaki sınıflandırıcıyla simülatörün bütün notlarında aynı sonucu verir."""
    from agents.memory import classify as domain_classify
    from cm.core import classify, find_sensitive

    notes = Services.create(mode="mock").run.notes()
    diff = [n["text"] for n in notes if classify(n["text"]) != domain_classify(n["text"])]
    assert len(notes) > 2000 and not diff, diff[:3]
    assert classify("asansör yok, 4. kata merdivenle çıkılıyor") == "building_access"
    assert classify("numara tabelası yok, eczanenin yanındaki yeşil boyalı bina") == "directions"
    assert find_sensitive("kapı şifresi 2580") and find_sensitive("Ahmet bey arayın") and not find_sensitive("arka sokaktaki otopark")


def test_error_is_streamed_not_raised(rt):
    assert _run(rt, ScriptedModel([]), {"actorId": "O02"}) == [{"error": "İstek gövdesinde `prompt` yok."}]
    ev = _run(rt, ScriptedModel([]), {"prompt": "x", "actorId": "O02"})      # betik boş: model hatası akışa yazılır
    assert ev and "error" in ev[-1]


def test_model_id_must_be_inference_profile():
    from cm.model import DEFAULT_MODEL_ID, check_model_id

    assert check_model_id(DEFAULT_MODEL_ID).startswith("global.")
    with pytest.raises(ValueError):
        check_model_id("anthropic.claude-sonnet-4-6")


def test_memory_session_manager_optional(monkeypatch):
    from cm.memory import session_manager

    monkeypatch.delenv("MEMORY_AGENTMEMORY_ID", raising=False)
    assert session_manager("O02", "s" * 33) is None
