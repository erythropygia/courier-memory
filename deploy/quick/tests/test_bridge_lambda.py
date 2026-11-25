"""Quick köprüsü Lambda'sı: Gateway'den gelen araç çağrısını supervisor runtime'ına iletir. AWS'ye gitmez."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bridge_lambda as bl  # noqa: E402


class _Body:
    def __init__(self, lines):
        self.lines, self.closed = lines, False

    def iter_lines(self):
        yield from self.lines

    def close(self):
        self.closed = True


class _Client:
    def __init__(self, lines=None, error=None):
        self.lines, self.error, self.calls, self.body = lines or [], error, [], None

    def invoke_agent_runtime(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        self.body = _Body(self.lines)
        return {"response": self.body}


class _Ctx:
    def __init__(self, tool="courier-memory___ask_courier_memory"):
        self.client_context = type("CC", (), {"custom": {"bedrockAgentCoreToolName": tool}})()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/CM_default_agent-x")
    monkeypatch.setenv("QUICK_ACTOR_ID", "MUDUR-QUICK")


def test_forwards_question_with_fixed_identity(env, monkeypatch):
    client = _Client([b'data: {"event": {"contentBlockDelta": {"delta": {"text": "Plan hazir."}}}}'])
    monkeypatch.setattr(bl, "_client", lambda: client)
    out = bl.handler({"question": "Bugunun plani?", "day": 32, "actorId": "O02"}, _Ctx())
    assert out == {"answer": "Plan hazir."}
    sent = json.loads(client.calls[0]["payload"])
    assert sent == {"prompt": "Bugunun plani?", "actorId": "MUDUR-QUICK", "day": 32}     # kimlik olaydan değil ortamdan
    assert len(client.calls[0]["runtimeSessionId"]) >= 33 and client.body.closed


def test_rejects_unknown_tool_and_empty_question(env, monkeypatch):
    monkeypatch.setattr(bl, "_client", lambda: _Client())
    assert "error" in bl.handler({"question": "x"}, _Ctx(tool="other___delete_everything"))
    assert "error" in bl.handler({"question": "   "}, _Ctx())
    assert "error" in bl.handler({"question": "x" * 5000}, _Ctx())


def test_agent_error_and_aws_error_are_reported_safely(env, monkeypatch):
    from botocore.exceptions import ClientError

    monkeypatch.setattr(bl, "_client", lambda: _Client([b'data: {"error": "Timeout"}']))
    assert bl.handler({"question": "Plan?"}, _Ctx()) == {"error": "Ajan yanıt veremedi: Timeout"}
    err = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "arn:aws:iam::111122223333:role/x"}}, "InvokeAgentRuntime")
    monkeypatch.setattr(bl, "_client", lambda: _Client(error=err))
    out = bl.handler({"question": "Plan?"}, _Ctx())
    assert "AccessDeniedException" in out["error"] and "111122223333" not in out["error"]


def test_parse_stream_joins_messages():
    lines = [b'data: {"event": {"messageStart": {}}}', b'data: {"event": {"contentBlockDelta": {"delta": {"text": "A"}}}}',
             b'data: {"event": {"messageStart": {}}}', b'data: {"event": {"contentBlockDelta": {"delta": {"text": "B"}}}}']
    assert bl.parse_stream(lines) == "A\nB"


def _tr(**kw):
    return ('data: ' + json.dumps({"cm_trace": {"seq": 0, "parent": None, "tool": None, **kw}})).encode()


def test_answer_gets_one_line_chain_path(env, monkeypatch):
    lines = [_tr(agent="supervisor", type="tool_call", tool="ask_planner"),
             _tr(agent="planner", parent="supervisor", type="delegate_start"),
             _tr(agent="planner", parent="supervisor", type="tool_call", tool="plan_day"),
             _tr(agent="planner", parent="supervisor", type="tool_result", tool="plan_day"),
             _tr(agent="analyst", parent="supervisor", type="delegate_start"),
             _tr(agent="analyst", parent="supervisor", type="tool_call", tool="query_history"),
             _tr(agent="analyst", parent="supervisor", type="tool_call", tool="query_history"),
             b'data: {"event": {"contentBlockDelta": {"delta": {"text": "Plan hazir."}}}}']
    monkeypatch.setattr(bl, "_client", lambda: _Client(lines))
    out = bl.handler({"question": "Plan?"}, _Ctx())
    assert out["answer"] == "Plan hazir.\n\nYol: Supervisor → Planlama (plan_day) → Analiz (query_history)"


def test_denied_hop_is_shown_and_no_trace_means_no_footer(env, monkeypatch):
    lines = [_tr(agent="supervisor", type="denied", tool="ask_planner"),
             b'data: {"event": {"contentBlockDelta": {"delta": {"text": "Yetki yok."}}}}']
    monkeypatch.setattr(bl, "_client", lambda: _Client(lines))
    assert bl.handler({"question": "Plan?"}, _Ctx())["answer"] == "Yetki yok.\n\nYol: Supervisor → ret (ask_planner)"
    monkeypatch.setattr(bl, "_client", lambda: _Client([b'data: {"event": {"contentBlockDelta": {"delta": {"text": "X"}}}}']))
    assert bl.handler({"question": "Plan?"}, _Ctx())["answer"] == "X"
