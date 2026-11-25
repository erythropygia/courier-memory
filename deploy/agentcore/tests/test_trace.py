"""Canlı zincir izi (`cm_trace`): araç adımları, ret, supervisor'ın uzman izini aktarması; Bedrock'a ve AgentCore'a gitmez.

Model betikli sahte modelle, uzman runtime'ı sahte `InvokeAgentRuntime` akışıyla sınanır.
"""
import json
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("strands")
pytest.importorskip("bedrock_agentcore")

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_multi_agent import _Client, _Resp  # noqa: E402
from test_runtime import ScriptedModel, _fresh, _run, _text, _tool_results  # noqa: E402

FIELDS = {"seq", "agent", "parent", "type", "tool", "input", "summary", "ms", "ok"}


def _traces(events):
    return [e["cm_trace"] for e in events if "cm_trace" in e]


def _kinds(events):
    """Akış sırası: model olayı `m:<tür>`, iz `t:<tür>`."""
    out = []
    for e in events:
        if "cm_trace" in e:
            out.append(f"t:{e['cm_trace']['type']}")
        elif "event" in e:
            out.append(f"m:{next(iter(e['event']))}")
    return out


def _sse(item) -> bytes:
    return ("data: " + json.dumps(item, ensure_ascii=False)).encode("utf-8")


@pytest.fixture
def runtime_role(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "core")

    def use(role):
        monkeypatch.setenv("CM_AGENT_ROLE", role)
        return main

    yield use
    be.reset_backend()
    main._agents.clear()
    main._model = None


# ------------------------------------------------------------------ tek runtime: kendi araçları
def test_tool_call_and_result_are_ordered_between_model_events(runtime_role):
    main = runtime_role("courier")
    model = ScriptedModel([{"tool": "stop_cards", "input": {"courier_id": "O02"}}, {"text": "Kartlar hazır."}])
    ev = _run(main, model, {"prompt": "Kartlarım?", "actorId": "O02"})
    tr = _traces(ev)
    assert [t["type"] for t in tr] == ["tool_call", "tool_result"] and not [e for e in ev if "error" in e]
    assert all(set(t) == FIELDS for t in tr) and [t["seq"] for t in tr] == [1, 2]
    call, res = tr
    assert call == {"seq": 1, "agent": "courier", "parent": None, "type": "tool_call", "tool": "stop_cards",
                    "input": {"courier_id": "O02"}, "summary": "stop_cards çağrılıyor", "ms": None, "ok": None}
    assert res["agent"] == "courier" and res["tool"] == "stop_cards" and res["ok"] is True
    assert isinstance(res["ms"], int) and 0 < len(res["summary"]) <= 400
    kinds = _kinds(ev)
    first_stop, second_start = kinds.index("m:messageStop"), [i for i, k in enumerate(kinds) if k == "m:messageStart"][1]
    assert first_stop < kinds.index("t:tool_call") < kinds.index("t:tool_result") < second_start
    assert _text(ev) == "Kartlar hazır."


def test_tool_result_summary_is_compact_json_overview():
    from cm.trace import summarize_result

    s = summarize_result(json.dumps({"courier": "O02", "stops": [1, 2, 3], "warnings": {"a": 1}, "note": None}))
    assert s == "courier=O02, stops: 3 öğe, warnings: 1 alan"
    assert summarize_result(json.dumps({"error": "Bilinmeyen kurye"})) == "hata: Bilinmeyen kurye"
    assert len(summarize_result(json.dumps({f"k{i}": "x" * 50 for i in range(40)}))) <= 400
    assert summarize_result("düz metin") == "düz metin"


def test_failed_tool_reports_ok_false(runtime_role):
    main = runtime_role("courier")
    model = ScriptedModel([{"tool": "stop_cards", "input": {"courier_id": "O02", "day": 999}}, {"text": "Olmadı."}])
    ev = _run(main, model, {"prompt": "Kartlar", "actorId": "O02"})
    res = _traces(ev)[-1]
    assert res["type"] == "tool_result" and res["ok"] is False and res["summary"].startswith("hata:")


def test_scope_denial_emits_denied_without_tool_result(runtime_role):
    main = runtime_role("courier")
    model = ScriptedModel([{"tool": "stop_cards", "input": {"courier_id": "K07"}}, {"text": "Paylaşamam."}])
    ev = _run(main, model, {"prompt": "K07 kartları", "actorId": "O02"})
    tr = _traces(ev)
    assert [t["type"] for t in tr] == ["denied"]
    assert tr[0]["tool"] == "stop_cards" and tr[0]["input"] == {"courier_id": "K07"}
    assert "Erişim reddedildi" in tr[0]["summary"] and tr[0]["ok"] is None
    assert _tool_results(model)[0]["status"] == "error"                       # modele giden ret değişmedi


def test_secrets_in_input_are_masked(runtime_role):
    main = runtime_role("all")
    note = "Ayşe hanım 0532 111 22 33, kapı şifresi 2580, park yok"
    model = ScriptedModel([{"tool": "leave_note", "input": {"courier_id": "O02", "text": note}}, {"text": "Not alındı."}])
    ev = _run(main, model, {"prompt": "not", "actorId": "O02"})
    blob = json.dumps(_traces(ev), ensure_ascii=False)
    assert "2580" not in blob and "0532" not in blob and "Ayşe" not in blob and '"agent": "all"' in blob


def test_each_request_has_its_own_sequence(runtime_role):
    main = runtime_role("courier")
    step = [{"tool": "stop_cards", "input": {"courier_id": "O02"}}, {"text": "Tamam."}]
    model = ScriptedModel(step * 2)                                       # aynı oturum: ajan önbellekte, kuyruk yeni
    for _ in range(2):
        ev = _run(main, model, {"prompt": "Kartlar", "actorId": "O02"})
        assert [t["seq"] for t in _traces(ev)] == [1, 2]


def test_sink_is_thread_safe_and_seq_ordered():
    from cm.trace import TraceSink

    sink = TraceSink("courier")
    threads = [threading.Thread(target=lambda: [sink.emit("tool_call", tool="x") for _ in range(200)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = [i["cm_trace"]["seq"] for i in sink.drain()]
    assert seqs == list(range(1, 801)) and sink.drain() == []


# ------------------------------------------------------------------ supervisor: uzman izini aktarma
SPECIALIST_STREAM = [
    _sse({"event": {"messageStart": {"role": "assistant"}}}),
    _sse({"cm_trace": {"seq": 1, "agent": "planner", "parent": None, "type": "tool_call", "tool": "plan_day",
                       "input": {"day": 32}, "summary": "plan_day çağrılıyor", "ms": None, "ok": None}}),
    _sse({"cm_trace": {"seq": 2, "agent": "planner", "parent": None, "type": "tool_result", "tool": "plan_day",
                       "input": None, "summary": "day=32, assignments: 9 öğe", "ms": 41, "ok": True}}),
    b"",
    _sse({"event": {"messageStart": {"role": "assistant"}}}),
    _sse({"event": {"contentBlockDelta": {"delta": {"text": "Plan hazır: 9 kurye."}}}}),
]


def test_parse_stream_answer_unchanged_and_forwards_traces():
    from cm.delegate import parse_stream

    got = []
    assert parse_stream(SPECIALIST_STREAM) == "Plan hazır: 9 kurye."                    # izsiz tüketici
    assert parse_stream(SPECIALIST_STREAM, got.append) == "Plan hazır: 9 kurye."
    assert [g["type"] for g in got] == ["tool_call", "tool_result"]


@pytest.fixture
def supervisor(runtime_role, monkeypatch):
    main = runtime_role("supervisor")
    from cm import delegate

    monkeypatch.setattr(delegate, "_arn", lambda role: f"arn:x:runtime/CM-{role}")
    return main, delegate, monkeypatch


def test_supervisor_forwards_specialist_trace_with_parent_and_renumbered_seq(supervisor):
    main, delegate, monkeypatch = supervisor
    client = _Client(_Resp(SPECIALIST_STREAM))
    monkeypatch.setattr(delegate, "_runtime_client", lambda: client)
    model = ScriptedModel([{"tool": "ask_planner", "input": {"question": "Bugünün planı?", "day": 32}},
                           {"text": "Planlama Ajanı: 9 kurye."}])
    ev = _run(main, model, {"prompt": "Plan?", "actorId": "MUDUR-01"})
    tr = _traces(ev)
    assert [(t["agent"], t["type"]) for t in tr] == [
        ("supervisor", "tool_call"), ("planner", "delegate_start"), ("planner", "tool_call"),
        ("planner", "tool_result"), ("planner", "delegate_end"), ("supervisor", "tool_result")]
    assert [t["seq"] for t in tr] == [1, 2, 3, 4, 5, 6]
    assert [t["parent"] for t in tr] == [None, "supervisor", "supervisor", "supervisor", "supervisor", None]
    start, fwd_call, fwd_res, end = tr[1:5]
    assert start["input"] == {"question": "Bugünün planı?", "day": 32} and start["tool"] is None
    assert fwd_call["tool"] == "plan_day" and fwd_call["input"] == {"day": 32}
    assert fwd_res["ms"] == 41 and fwd_res["ok"] is True and fwd_res["summary"] == "day=32, assignments: 9 öğe"
    assert end["ok"] is True and isinstance(end["ms"], int) and end["summary"] == "Plan hazır: 9 kurye."
    assert tr[5]["tool"] == "ask_planner" and tr[5]["ok"] is True
    assert _tool_results(model)[0]["content"][0]["text"] == "Plan hazır: 9 kurye."     # cevap metni izden etkilenmez
    assert json.loads(client.calls[0]["payload"])["actorId"] == "MUDUR-01"
    assert _text(ev) == "Planlama Ajanı: 9 kurye." and not [e for e in ev if "error" in e]


def test_supervisor_delegation_error_emits_error_then_tool_error(supervisor):
    main, delegate, monkeypatch = supervisor
    monkeypatch.setattr(delegate, "_runtime_client", lambda: _Client(_Resp([_sse({"error": "Timeout"})])))
    model = ScriptedModel([{"tool": "ask_planner", "input": {"question": "Plan?"}}, {"text": "Ulaşılamadı."}])
    ev = _run(main, model, {"prompt": "Plan?", "actorId": "MUDUR-01"})
    tr = _traces(ev)
    assert [(t["agent"], t["type"]) for t in tr] == [
        ("supervisor", "tool_call"), ("planner", "delegate_start"), ("planner", "error"),
        ("planner", "delegate_end"), ("supervisor", "tool_result")]
    err, end, res = tr[2:]
    assert err["parent"] == "supervisor" and "Timeout" in err["summary"] and err["ok"] is None
    assert end["ok"] is False and isinstance(end["ms"], int)
    assert res["ok"] is False and "Timeout" in res["summary"]
    assert _tool_results(model)[0]["status"] == "error" and _text(ev) == "Ulaşılamadı."


def test_supervisor_denial_never_starts_delegation(supervisor):
    main, delegate, monkeypatch = supervisor
    client = _Client(_Resp(SPECIALIST_STREAM))
    monkeypatch.setattr(delegate, "_runtime_client", lambda: client)
    model = ScriptedModel([{"tool": "ask_planner", "input": {"question": "Plan?"}}, {"text": "Yetkin yok."}])
    ev = _run(main, model, {"prompt": "Plan?", "actorId": "O02"})
    assert [(t["agent"], t["type"]) for t in _traces(ev)] == [("supervisor", "denied")] and client.calls == []


def test_forward_drops_malformed_items():
    from cm.trace import TraceSink

    sink = TraceSink("supervisor")
    assert sink.forward("bozuk") is None and sink.forward({"type": "hack"}) is None
    item = sink.forward({"type": "tool_call", "agent": "kötü", "ms": "x", "ok": "yes", "input": [1]})
    assert item["agent"] == "supervisor" and item["ms"] is None and item["ok"] is None and item["input"] is None


def test_trace_is_flushed_live_while_a_tool_is_still_running():
    """Uzun araç (uzman çağrısı) sürerken iz beklemez: tüketici izi alır, sonraki model olayı ondan sonra gelir."""
    import asyncio

    import main
    from cm.trace import TraceSink

    sink = TraceSink("supervisor")

    async def go():
        seen = asyncio.Event()

        async def stream():
            yield {"event": {"messageStart": {"role": "assistant"}}}
            threading.Thread(target=lambda: sink.emit("delegate_start", agent="planner", parent="supervisor")).start()
            await asyncio.wait_for(seen.wait(), timeout=2)        # iz canlı akmasaydı burada zaman aşımı olurdu
            yield {"event": {"messageStop": {"stopReason": "end_turn"}}}

        out = []
        async for item in main._with_trace(stream(), sink):
            out.append(item)
            if "cm_trace" in item:
                seen.set()
        return out

    assert _kinds(asyncio.run(go())) == ["m:messageStart", "t:delegate_start", "m:messageStop"]
