import json

import pytest

from agents import Services
from agents.guardrails import find_pii, redact
from agents.memory import classify
from agents.llm import LLM, AgentError, Tool, obj
from agents.memorybook import MemoryWriteError
from agents.tr import dative, num


@pytest.fixture
def sv(tmp_path):
    return Services.create(mode="mock", memory_file=tmp_path / "mem.json")


def test_guardrails():
    assert find_pii("Ayşe hanım çok huysuz") and find_pii("0555 000 00 00 arayın") and find_pii("yaşlı teyze")
    assert not find_pii("Zil çalışmıyor; alıcıyı telefonla arayın.")
    assert "Ayşe" not in redact("zil bozuk, Ayşe hanım çok huysuz")


def test_memory_rejects_pii(sv):
    sv.book.ensure(sv.run.eval_days[0])
    with pytest.raises(MemoryWriteError):
        sv.book.upsert(address=1, kind="bell", text="Ayşe hanım huysuz, zil bozuk", day=sv.run.eval_days[0], note_id=None)


def test_classify():
    assert classify("cmt kapalı boşuna gelmeyin") == "saturday_closed"
    assert classify("yol çalışması var sokak kapalı arkadan dolan") == "roadwork"
    assert classify("zil çalışmıyo kapıyı çal") == "bell"
    assert classify("trafik berbattı bugün") is None


def test_tr_helpers():
    assert dative(3) == "'e" and dative(6) == "'ya" and dative(10) == "'a" and dative(20) == "'ye"
    assert num(1234.5) == "1.234,5" and num(-3.8, sign=True) == "-3,8"


def test_assignment_mock_beats_random(sv):
    d = sv.run.meta["critical"]["day"]
    r = sv.assignment.propose(d)
    assert r["total"]["expected_fails"] < r["comparison"]["history_blind_expected_fails"]
    assert len({x["courier"] for x in r["assignment"]}) == len(r["assignment"])


def test_replay_without_cassette_degrades(tmp_path):
    sv = Services.create(mode="replay", memory_file=tmp_path / "m.json")
    sv.assignment.llm.cassette_dir = tmp_path / "offline"
    d = sv.run.meta["critical"]["day"]
    r = sv.assignment.propose(d)
    assert r["degraded"] is True and r["assignment"]


class FakeLLM(LLM):
    """Kayıtlı yanıtları sırayla döndürür: canlı döngünün mantığını ağ olmadan sınar."""

    def __init__(self, responses):
        super().__init__(mode="live")
        self.responses = list(responses)
        self.requests = []

    def _call(self, agent, req):
        self.requests.append(json.loads(json.dumps(req, default=str)))
        return self.responses.pop(0)


def test_agent_loop_tool_then_finish():
    calls = []
    tools = [Tool("add", "iki sayıyı toplar", obj({"a": {"type": "integer"}, "b": {"type": "integer"}}),
                  lambda i: calls.append(i) or {"result": i["a"] + i["b"]}),
             Tool("finish", "sonuç", obj({"answer": {"type": "integer"}}))]
    llm = FakeLLM([
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t1", "name": "add", "input": {"a": 2, "b": 3}}]},
        {"stop_reason": "tool_use", "content": [{"type": "text", "text": "tamam"},
                                               {"type": "tool_use", "id": "t2", "name": "finish", "input": {"answer": 5}}]},
    ])
    run = llm.run_agent(agent="t", system="s", user="2+3?", tools=tools, finish_tool="finish")
    assert run.final_input == {"answer": 5} and calls == [{"a": 2, "b": 3}]
    req = llm.requests[0]
    assert all(t["strict"] for t in req["tools"]) and "tool_choice" not in req and "temperature" not in req
    assert req["output_config"]["effort"] == "medium" and "thinking" not in req
    assert llm.requests[1]["messages"][-1]["content"][0]["tool_use_id"] == "t1"


def test_agent_loop_refusal_and_tool_error():
    llm = FakeLLM([{"stop_reason": "refusal", "content": []}])
    with pytest.raises(AgentError):
        llm.run_agent(agent="t", system="s", user="x", tools=[])
    boom = Tool("explode", "error", obj({}), lambda i: 1 / 0)
    llm = FakeLLM([
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t1", "name": "explode", "input": {}}]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "özür"}]},
    ])
    run = llm.run_agent(agent="t", system="s", user="x", tools=[boom])
    assert run.final_text == "özür"
    assert llm.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_memory_live_path_with_fake_llm(sv):
    d = sv.run.meta["critical"]["day"]
    c = sv.run.meta["critical"]["courier"]
    stop = sv.run.route_of(d, c)["stops"][2]
    a = int(stop[0])
    fake = FakeLLM([
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "1", "name": "near_addresses",
                                                 "input": {"lat": stop[1], "lng": stop[2], "radius_m": 80}}]},
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "2", "name": "write_memory",
                                                 "input": {"address_id": a, "type": "bell", "hint": "Ayşe hanım huysuz, zil bozuk"}}]},
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "3", "name": "write_memory",
                                                 "input": {"address_id": a, "type": "bell", "hint": "Zil çalışmıyor; telefonla arayın."}}]},
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "4", "name": "report_result", "input": {
            "status": "saved", "address_id": a, "type": "bell", "hint": "Zil çalışmıyor; telefonla arayın.",
            "personal_data_redacted": True, "summary": "ok", "question": None}}]},
    ])
    sv.memory.llm = fake
    r = sv.memory.process(d, c, "zil bozuk Ayşe hanım huysuz", stop[1], stop[2])
    assert r["status"] == "saved" and not r["degraded"]
    assert any("kişisel veri" in s["summary"] for s in r["steps"])        # araç PII'yi reddetti, ajan yeniden yazdı
    assert sv.book.for_address(a, d)[-1]["text"] == "Zil çalışmıyor; telefonla arayın."
