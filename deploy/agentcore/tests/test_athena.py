"""Analiz Ajanı (Athena SQL), Hasat aracı ve bunların kimlik sınırı. AWS'ye gitmez: Athena istemcisi sahte."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("strands")
pytest.importorskip("bedrock_agentcore")

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_runtime import HAS_DOMAIN, ScriptedModel, _fresh, _run, _tool_results, needs_domain  # noqa: E402,F401


# ------------------------------------------------------------------ SQL koruması
@pytest.mark.parametrize("sql", [
    "SELECT day, count(*) FROM deliveries GROUP BY day",
    "  with t as (select * from daily_metrics where arm = 'D') select avg(fail) from t ;",
    "select a.kind, avg(d.absent) from deliveries d join addresses a on a.id = d.address_id group by 1",
])
def test_validate_sql_accepts_single_select_and_caps_rows(sql):
    from cm.athena import MAX_ROWS, validate_sql

    q = validate_sql(sql)
    assert q.endswith(f"LIMIT {MAX_ROWS}") and ";" not in q


@pytest.mark.parametrize("sql", [
    "DROP TABLE deliveries", "select 1; drop table deliveries", "INSERT INTO couriers VALUES ('x')",
    "CREATE TABLE x AS SELECT * FROM deliveries", "UNLOAD (SELECT * FROM deliveries) TO 's3://x/'",
    "select * from deliveries -- yorum", "select /* gizli */ 1", "SHOW TABLES", "DESCRIBE deliveries",
    "select * from other_db.secret", "", "   ", "MSCK REPAIR TABLE deliveries", "ALTER TABLE x ADD COLUMNS (y int)",
])
def test_validate_sql_rejects_everything_else(sql):
    from cm.athena import QueryRejected, validate_sql

    with pytest.raises(QueryRejected):
        validate_sql(sql)


# ------------------------------------------------------------------ sorgu çalıştırma (sahte Athena)
class FakeAthena:
    def __init__(self, states, rows=None, reason=None):
        self.states, self.rows, self.reason, self.started, self.stopped = list(states), rows or [], reason, [], []

    def start_query_execution(self, **kw):
        self.started.append(kw)
        return {"QueryExecutionId": "q-1"}

    def get_query_execution(self, QueryExecutionId):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"QueryExecution": {"Status": {"State": state, "StateChangeReason": self.reason},
                                   "Statistics": {"DataScannedInBytes": 2048}}}

    def get_query_results(self, QueryExecutionId, MaxResults):
        def row(vals):
            return {"Data": [{"VarCharValue": v} for v in vals]}
        return {"ResultSet": {"Rows": [row(["day", "fails"]), *[row(r) for r in self.rows]]}}

    def stop_query_execution(self, QueryExecutionId):
        self.stopped.append(QueryExecutionId)


def test_run_query_uses_workgroup_and_database(monkeypatch):
    from cm import athena

    monkeypatch.setenv("CM_ATHENA_WORKGROUP", "wg-test")
    monkeypatch.setenv("CM_ATHENA_DATABASE", "db_test")
    fake = FakeAthena(["QUEUED", "RUNNING", "SUCCEEDED"], rows=[["20", "99"], ["21", "87"]])
    out = athena.run_query("select day, fail as fails from daily_metrics", client=fake, sleep=lambda s: None)
    assert out == {"columns": ["day", "fails"], "rows": [["20", "99"], ["21", "87"]], "row_count": 2,
                   "truncated": False, "scanned_kb": 2.0}
    kw = fake.started[0]
    assert kw["WorkGroup"] == "wg-test" and kw["QueryExecutionContext"] == {"Database": "db_test"}
    assert kw["QueryString"].endswith(f"LIMIT {athena.MAX_ROWS}")


def test_run_query_reports_sql_error_and_timeout(monkeypatch):
    from cm import athena

    failed = FakeAthena(["FAILED"], reason="COLUMN_NOT_FOUND: line 1:8: Column 'x' cannot be resolved")
    with pytest.raises(athena.QueryFailed, match="COLUMN_NOT_FOUND"):
        athena.run_query("select x from deliveries", client=failed, sleep=lambda s: None)
    slow = FakeAthena(["RUNNING"])
    clock = iter(range(0, 10_000, 10))
    with pytest.raises(athena.QueryFailed, match="süre"):
        athena.run_query("select 1", client=slow, sleep=lambda s: None, now=lambda: next(clock))
    assert slow.stopped == ["q-1"]                                          # zaman aşımında sorgu durdurulur


def test_query_history_tool_returns_json_or_explains(monkeypatch):
    from cm import athena

    monkeypatch.setattr(athena, "_client", lambda: FakeAthena(["SUCCEEDED"], rows=[["20", "99"]]))
    assert json.loads(athena.query_history(sql="select day, fail as fails from daily_metrics"))["rows"] == [["20", "99"]]
    rejected = json.loads(athena.query_history(sql="drop table deliveries"))
    assert "error" in rejected and "SELECT" in rejected["error"]


# ------------------------------------------------------------------ kimlik sınırı
def test_scope_manager_only_for_analysis_and_harvest():
    from cm.scope import decide

    for name in ("query_history", "harvest_questions", "ask_analyst"):
        assert "müdür" in decide("O02", "courier", name, {})
        assert "müdür" in decide("default", "guest", name, {})
        assert decide("MUDUR-01", "manager", name, {}) is None


def test_analyst_runtime_has_only_query_tool_and_prompt(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "core")
    monkeypatch.setenv("CM_AGENT_ROLE", "analyst")
    from cm import athena

    monkeypatch.setattr(athena, "_client", lambda: FakeAthena(["SUCCEEDED"], rows=[["20", "99"]]))
    try:
        model = ScriptedModel([{"tool": "query_history", "input": {"sql": "select day, fail as fails from daily_metrics"}},
                               {"text": "20. gün 99 başarısız."}])
        _run(main, model, {"prompt": "Gün gün başarısız teslim?", "actorId": "MUDUR-01"})
        assert model.calls[0]["tools"] == ["query_history"] and "Analiz Ajanı" in model.calls[0]["system"]
        assert "deliveries" in model.calls[0]["system"]                    # şema istemde: model tabloları bilir
        assert _tool_results(model)[0]["status"] == "success"
        denied = ScriptedModel([{"tool": "query_history", "input": {"sql": "select 1"}}, {"text": "Yetkin yok."}])
        main._agents.clear()
        _run(main, denied, {"prompt": "sorgu", "actorId": "O02"})
        assert _tool_results(denied)[0]["status"] == "error"
    finally:
        be.reset_backend()
        main._agents.clear()
        main._model = None


# ------------------------------------------------------------------ Hasat
@needs_domain
def test_harvest_questions_full_toolset(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "full")
    try:
        from cm.tools import harvest_questions

        h = json.loads(harvest_questions())
        assert h["summary"] and h["questions"] and h["plan_source"]
        assert all(q["courier_id"] and q["question"] and q["address"] for q in h["questions"])
    finally:
        be.reset_backend()


def test_harvest_questions_core_explains(tmp_path, monkeypatch):
    main, be = _fresh(tmp_path, monkeypatch, "core")
    try:
        from cm.tools import harvest_questions

        with pytest.raises(ValueError, match="çekirdek"):
            harvest_questions()
    finally:
        be.reset_backend()
