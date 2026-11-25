"""AgentCore zinciri (api/agentcore_chain.py): altı adım sırayla, cm_trace → canlı olay (iç içe, ret), cm_trace'siz yedek,
AWS ayrıntısı sızdırmayan hata adımı, koşu sürerken 409, kapalıyken 501. boto3 sahte; AWS'ye gidilmez."""
import json
import threading
import time

import pytest
from botocore.exceptions import ClientError, NoCredentialsError, ReadTimeoutError
from fastapi.testclient import TestClient

from api import agentcore_chain as AC
from api import agentcore_client as ACC
from api import live as L
from api.main import app

ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/CourierMemory_default_agent-AbCdEf1234"
ASK = {"planner": "ask_planner", "courier": "ask_courier_agent", "memory_keeper": "ask_memory_keeper", "analyst": "ask_analyst"}


def data(obj) -> bytes:
    return ("data: " + json.dumps(obj, ensure_ascii=False)).encode("utf-8")


def text(s):
    return [data({"event": {"messageStart": {"role": "assistant"}}}),
            data({"event": {"contentBlockDelta": {"delta": {"text": s[:5]}}}}),
            data({"event": {"contentBlockDelta": {"delta": {"text": s[5:]}}}})]


def tool_use(name, inp):
    return [data({"event": {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": "t1"}}}}}),
            data({"event": {"contentBlockDelta": {"delta": {"toolUse": {"input": inp[:4]}}}}}),
            data({"event": {"contentBlockDelta": {"delta": {"toolUse": {"input": inp[4:]}}}}}),
            data({"event": {"contentBlockStop": {}}})]


def tr(seq, agent, typ, parent=None, **kw):
    return data({"cm_trace": {"seq": seq, "agent": agent, "parent": parent, "type": typ, **kw}})


def traced(st: AC.Step) -> list[bytes]:
    """Runtime'ın yazacağı gibi: Supervisor ask_* → uzman alan aracı → sonuç (ya da ret)."""
    ask = ASK[st.agent]
    lines = tool_use(ask, json.dumps({"question": st.prompt}, ensure_ascii=False))
    if st.expect == "denied":
        return lines + [tr(1, "supervisor", "tool_call", tool=ask, input={"question": st.prompt}),
                        tr(2, "supervisor", "denied", tool=ask, summary="Kurye kimliği planlama ajanına soramaz", ok=False)] \
            + text("Bu bilgi yalnız müdüre açık.")
    return lines + [tr(1, "supervisor", "tool_call", tool=ask, input={"question": st.prompt}),
                    tr(2, st.agent, "delegate_start", "supervisor", tool=ask),
                    tr(3, st.agent, "tool_call", "supervisor", tool=st.tool, input={"day": 32}),
                    tr(4, st.agent, "tool_result", "supervisor", tool=st.tool, summary=f"{st.tool} tamam", ms=41.6, ok=True),
                    tr(5, st.agent, "delegate_end", "supervisor", tool=ask, ms=1200, ok=True),
                    tr(6, "supervisor", "tool_result", tool=ask, summary="uzman yanıtladı", ok=True)] \
        + text(f"Yanıt: {st.tool}")


class Body:
    def __init__(self, lines):
        self.lines, self.closed = lines, False

    def iter_lines(self):
        yield from self.lines

    def close(self):
        self.closed = True


class Fake:
    """Sahte boto3: `bedrock-agentcore-control` ve `bedrock-agentcore`."""

    def __init__(self, script=traced, listing=None, list_error=None, invoke_error=None, gate=None):
        self.script, self.list_error, self.invoke_error, self.gate = script, list_error, invoke_error, gate
        self.listing = listing if listing is not None else [{"agentRuntimeName": "CourierMemory_default_planner", "agentRuntimeArn": "x"},
                                                            {"agentRuntimeName": "CourierMemory_default_agent", "agentRuntimeArn": ARN}]
        self.calls, self.lists = [], 0

    def __call__(self, service):
        return self

    def list_agent_runtimes(self, **kw):
        self.lists += 1
        if self.list_error:
            raise self.list_error
        if "nextToken" not in kw:                     # iki sayfa: sayfalama izlenir
            return {"agentRuntimes": self.listing[:1], "nextToken": "p2"}
        return {"agentRuntimes": self.listing[1:]}

    def invoke_agent_runtime(self, **kw):
        if self.gate is not None:
            self.gate.wait(10)
        self.calls.append(kw)
        if self.invoke_error:
            raise self.invoke_error
        payload = json.loads(kw["payload"])
        st = next(s for s in AC.STEPS if s.prompt == payload["prompt"])
        return {"response": Body(self.script(st)), "contentType": "text/event-stream"}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(AC, "STEP_GAP", 0)
    monkeypatch.setattr(L, "LIVE", L.Live())
    import api.main as M
    monkeypatch.setattr(M, "LIVE", L.LIVE)
    monkeypatch.delenv(AC.ENABLE_ENV, raising=False)
    monkeypatch.delenv(ACC.NAME_ENV, raising=False)

    def use(fake):
        monkeypatch.setattr(ACC, "_DEFAULT", ACC.SupervisorClient(factory=fake))
        return fake
    return use


def wait(c, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get("/api/live").json()
        if s["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("AgentCore zinciri bitmedi")


def evs(s, t=None):
    return [e for e in s["events"] if t is None or e["t"] == t]


def test_six_steps_in_order_with_nested_hops_and_denied(env):
    gate = threading.Event()
    fake = env(Fake(gate=gate))
    c = TestClient(app)
    r = c.post("/api/live/start?chain=agentcore")
    assert r.status_code == 200 and r.json()["kind"] == "agentcore"
    assert c.post("/api/live/start?chain=agentcore").status_code == 409          # koşu sürerken ikisi de 409
    assert c.post("/api/live/start").status_code == 409
    gate.set()
    s = wait(c)
    assert s["status"] == "done" and s["kind"] == "agentcore"
    run = evs(s)[0]
    assert run["t"] == "run" and run["kind"] == "agentcore" and run["steps"] == 6 and len(run["chain"]) == 6
    assert evs(s)[-1]["t"] == "end"
    steps = evs(s, "step")
    assert [e["i"] for e in steps] == list(range(6))
    assert [e["actor"] for e in steps] == ["MUDUR-01", "O02", "O02", "MUDUR-01", "MUDUR-01", "O02"]
    assert not evs(s, "step_error")
    assert all(e["run"] == s["run_id"] and e["n"] == k for k, e in enumerate(s["events"]))

    res = {e["i"]: e["out"] for e in evs(s, "result")}
    assert res[0]["path"] == ["supervisor", "planner"] and "plan_day" in res[0]["tools"]
    assert res[1]["path"] == ["supervisor", "courier"] and "courier_briefing" in res[1]["tools"]
    assert res[2]["path"] == ["supervisor", "memory_keeper"] and "leave_note" in res[2]["tools"]
    assert "harvest_questions" in res[3]["tools"] and res[4]["path"] == ["supervisor", "analyst"]
    assert res[5]["denied"] is True and res[5]["path"] == ["supervisor"]
    assert res[0]["answer"] == "Yanıt: plan_day" and res[0]["traced"] is True

    ev = [e["e"] for e in evs(s, "ev")]
    nested = [e for e in ev if e["type"] == "tool" and e["agent"] == "planner"]
    assert nested and nested[0]["parent"] == "supervisor" and nested[0]["tool"] == "plan_day"
    top = [e for e in ev if e["type"] == "tool" and e["agent"] == "supervisor"]
    assert top and top[0]["parent"] is None and top[0]["target"] == "planner"
    assert any(e["type"] == "result" and e.get("ms") == 42 and e.get("ok") is True for e in ev)
    assert any(e["type"] == "delegate" and e["target"] == "planner" for e in ev)
    denied = [e for e in ev if e["type"] == "denied"]
    assert len(denied) == 1 and denied[0]["target"] == "planner" and "soramaz" in denied[0]["summary"]
    assert not [e for e in ev if e.get("fallback")]                       # cm_trace varken model olayından yinelenmez
    assert sum(1 for e in ev if e["type"] == "answer") == 6

    # oturum: ≥ 33 karakter, kimlik başına sabit; gün gövdede; ARN bir kez aranır; yeniden deneme yok
    sids = {json.loads(k["payload"])["actorId"]: set() for k in fake.calls}
    for k in fake.calls:
        sids[json.loads(k["payload"])["actorId"]].add(k["runtimeSessionId"])
        assert len(k["runtimeSessionId"]) >= 33 and k["agentRuntimeArn"] == ARN and k["accept"] == "text/event-stream"
        assert "day" in json.loads(k["payload"])
    assert len(fake.calls) == 6 and all(len(v) == 1 for v in sids.values()) and sids["O02"] != sids["MUDUR-01"]
    assert fake.lists == 2                                                 # iki sayfa, tek arama (önbellek)
    assert ARN not in json.dumps(s, ensure_ascii=False) and "123456789012" not in json.dumps(s)


def test_fallback_without_cm_trace_shows_supervisor_tools_and_text(env):
    def old(st):
        return tool_use(ASK[st.agent], json.dumps({"question": "plan?"})) + text("Eski dağıtım yanıtı")
    env(Fake(script=old))
    c = TestClient(app)
    assert c.post("/api/live/start?chain=agentcore").status_code == 200
    s = wait(c)
    assert s["status"] == "done" and not evs(s, "step_error")
    ev = [e["e"] for e in evs(s, "ev")]
    tools = [e for e in ev if e["type"] == "tool"]
    assert len(tools) == 6 and all(e["fallback"] and e["agent"] == "supervisor" for e in tools)
    assert tools[0]["tool"] == "ask_planner" and tools[0]["input"] == {"question": "plan?"} and tools[0]["target"] == "planner"
    res = {e["i"]: e["out"] for e in evs(s, "result")}
    assert res[0]["answer"] == "Eski dağıtım yanıtı" and res[0]["traced"] is False and res[0]["path"] == ["supervisor", "planner"]


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": f"User arn:aws:sts::123456789012:assumed-role/x is not authorized on {ARN}"}},
                       "InvokeAgentRuntime")


@pytest.mark.parametrize("kw,msg", [
    ({"list_error": NoCredentialsError()}, ACC.MSG_NO_CREDS),
    ({"list_error": _client_error("AccessDeniedException")}, ACC.MSG_DENIED),
    ({"invoke_error": _client_error("AccessDeniedException")}, ACC.MSG_DENIED),
    ({"listing": []}, ACC.MSG_MISSING),
    ({"invoke_error": _client_error("ResourceNotFoundException")}, ACC.MSG_MISSING),
])
def test_fatal_errors_become_one_friendly_failed_step(env, kw, msg):
    env(Fake(**kw))
    c = TestClient(app)
    c.post("/api/live/start?chain=agentcore")
    s = wait(c)
    assert s["status"] == "error"
    errs = evs(s, "step_error")
    assert [(e["i"], e["text"]) for e in errs] == [(0, msg)]
    assert [e["i"] for e in evs(s, "step")] == [0]                          # zincir durur, kalanı çalışmaz
    assert any(e["t"] == "http_done" and e["status"] == 502 for e in evs(s))
    dump = json.dumps(s, ensure_ascii=False)
    assert "arn:aws" not in dump and "123456789012" not in dump and "assumed-role" not in dump


def test_stream_error_and_timeout_fail_only_their_step(env):
    def script(st):
        if st.tool == "plan_day":
            return [data({"error": f"DelegationError: planner uzmanına şu an ulaşılamıyor; {ARN}"})]
        return traced(st)

    class Slow(Fake):
        def invoke_agent_runtime(self, **kw):
            if "brifing" in json.loads(kw["payload"])["prompt"]:
                raise ReadTimeoutError(endpoint_url=f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{ARN}")
            return super().invoke_agent_runtime(**kw)
    env(Slow(script=script))
    c = TestClient(app)
    c.post("/api/live/start?chain=agentcore")
    s = wait(c)
    assert s["status"] == "done"
    errs = {e["i"]: e["text"] for e in evs(s, "step_error")}
    assert set(errs) == {0, 1}
    assert errs[0].startswith("Supervisor hata döndürdü") and "<arn>" in errs[0]
    assert errs[1] == ACC.MSG_TIMEOUT
    assert {e["i"] for e in evs(s, "result")} == {2, 3, 4, 5}
    assert "123456789012" not in json.dumps(s)


def test_disabled_returns_501_and_day_chain_still_starts_flag(env, monkeypatch):
    monkeypatch.setenv(AC.ENABLE_ENV, "0")
    assert AC.enabled() is False
    c = TestClient(app)
    r = c.post("/api/live/start?chain=agentcore")
    assert r.status_code == 501 and "kapalı" in r.json()["detail"]
    assert c.post("/api/live/start?chain=bogus").status_code == 422
    assert c.get("/api/live").json()["status"] == "idle"
    monkeypatch.setenv(AC.ENABLE_ENV, "1")
    assert AC.enabled() is True


def test_map_trace_sanitises_and_keeps_nesting():
    e = AC.map_trace({"seq": "7", "agent": "Memory_Keeper", "parent": "supervisor", "type": "tool_call", "tool": "leave_note",
                      "input": {"text": f"not {ARN}"}, "ms": "12.4", "ok": True})
    assert (e["type"], e["agent"], e["parent"], e["tool"], e["seq"], e["ms"]) == ("tool", "memory_keeper", "supervisor", "leave_note", 7, 12)
    assert "arn:aws" not in json.dumps(e) and e["source"] == "agentcore"
    d = AC.map_trace({"agent": "supervisor", "type": "denied", "tool": "ask_planner", "summary": "izin yok 123456789012"})
    assert d["type"] == "denied" and d["parent"] is None and d["target"] == "planner" and "<hesap>" in d["summary"]
    x = AC.map_trace({"agent": "analyst", "parent": "supervisor", "type": "error", "tool": "query_history", "summary": "SQL reddedildi"})
    assert x["type"] == "error" and x["text"] == "SQL reddedildi"
    assert AC.map_trace({"type": "weird"})["type"] == "info"


def test_session_id_and_line_parsing():
    sid = ACC.session_id("1-O02")
    assert len(sid) >= 33 and sid.startswith("cm-live-1-o02-")
    assert ACC.parse_line(b": ping") is None and ACC.parse_line("data: [1]") is None and ACC.parse_line("data: {bad") is None
    assert ACC.parse_line('data: {"error": "x"}') == {"error": "x"}


def test_web_task_role_policy_is_scoped_to_supervisor():
    import importlib.util
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "deploy" / "web" / "ecs_deploy.py"
    spec = importlib.util.spec_from_file_location("ecs_deploy_for_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ENV["CM_AGENTCORE_CHAIN"] == "1" and mod.ENV["CM_AGENTCORE_SUPERVISOR"] == ACC.DEFAULT_NAME
    inv, lst = mod.agentcore_policy("us-east-1", "111122223333", ACC.DEFAULT_NAME)["Statement"]
    assert inv["Action"] == ["bedrock-agentcore:InvokeAgentRuntime"]
    assert inv["Resource"] == ["arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/CourierMemory_default_agent-*",
                               "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/CourierMemory_default_agent-*/runtime-endpoint/*"]
    assert lst["Action"] == ["bedrock-agentcore:ListAgentRuntimes"] and lst["Resource"] == "*"
