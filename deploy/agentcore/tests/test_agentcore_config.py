"""bootstrap.sh'in agentcore.json dönüşümü: supervisor + üç uzman runtime, ortam değişkenleri, IAM politikası."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentcore_config import (ANALYST_POLICY_PATH, ATHENA_BUCKET_PREFIX, ATHENA_DATABASE, ATHENA_WORKGROUP,  # noqa: E402
                              POLICY_PATH, SPECIALISTS, analyst_policy, configure)

TEMPLATE = {
    "name": "CourierMemory", "version": 2, "managedBy": "CDK",
    "runtimes": [{"name": "agent", "build": "CodeZip", "modelProvider": "Bedrock", "entrypoint": "main.py",
                  "codeLocation": "app/agent", "runtimeVersion": "PYTHON_3_14", "protocol": "HTTP"}],
    "memories": [{"name": "agentMemory", "eventExpiryDuration": 30, "strategies": []}],
}


def _env(runtime):
    return {e["name"]: e["value"] for e in runtime.get("envVars", [])}


def _by_name(cfg):
    return {r["name"]: r for r in cfg["runtimes"]}


def test_multi_agent_adds_specialists_sharing_code():
    original = copy.deepcopy(TEMPLATE)
    cfg, policy = configure(TEMPLATE, "CourierMemory", multi_agent=True)
    assert TEMPLATE == original                                          # girdi değişmez
    rts = _by_name(cfg)
    assert list(rts) == ["agent", *SPECIALISTS]
    for name in ("planner", "courier", "memory_keeper"):                # analyst ayrıca sınanır (Athena izni)
        r = rts[name]
        assert (r["codeLocation"], r["entrypoint"], r["build"]) == ("app/agent", "main.py", "CodeZip")
        assert _env(r) == {"CM_AGENT_ROLE": name, "UNIFIED_TRACES_DESTINATION_ENABLED": "true"}
        assert "additionalPolicies" not in r                             # uzman başka runtime çağıramaz
    sup = rts["agent"]
    assert _env(sup) == {"CM_AGENT_ROLE": "supervisor", "CM_RUNTIME_PREFIX": "CourierMemory_default_",
                         "UNIFIED_TRACES_DESTINATION_ENABLED": "true"}
    assert sup["additionalPolicies"] == [POLICY_PATH]
    assert cfg["memories"] == TEMPLATE["memories"]


def test_policy_is_scoped_to_this_project_and_target():
    _, policy = configure(TEMPLATE, "CourierMemory", multi_agent=True)
    invoke = next(s for s in policy["Statement"] if "bedrock-agentcore:InvokeAgentRuntime" in s["Action"])
    assert invoke["Resource"] == ["arn:aws:bedrock-agentcore:*:*:runtime/CourierMemory_default_*"]
    cfg, policy = configure(TEMPLATE, "CourierMemory", multi_agent=True, target="dev")
    assert _env(_by_name(cfg)["agent"])["CM_RUNTIME_PREFIX"] == "CourierMemory_dev_"
    assert policy["Statement"][0]["Resource"] == ["arn:aws:bedrock-agentcore:*:*:runtime/CourierMemory_dev_*"]
    actions = {a for s in policy["Statement"] for a in s["Action"]}
    assert actions == {"bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:ListAgentRuntimes"}


def test_analyst_gets_athena_env_and_read_only_policy():
    cfg, _ = configure(TEMPLATE, "CourierMemory", multi_agent=True)
    an = _by_name(cfg)["analyst"]
    assert _env(an) == {"CM_AGENT_ROLE": "analyst", "CM_ATHENA_DATABASE": ATHENA_DATABASE,
                        "CM_ATHENA_WORKGROUP": ATHENA_WORKGROUP, "UNIFIED_TRACES_DESTINATION_ENABLED": "true"}
    assert an["additionalPolicies"] == [ANALYST_POLICY_PATH]
    p = analyst_policy()
    actions = {a for s in p["Statement"] for a in s["Action"]}
    assert not any(a.startswith(("s3:Delete", "glue:Create", "glue:Delete", "glue:Update", "athena:Create", "athena:Delete"))
                   for a in actions)
    s3_write = next(s for s in p["Statement"] if "s3:PutObject" in s["Action"])
    assert s3_write["Resource"] == [f"arn:aws:s3:::{ATHENA_BUCKET_PREFIX}*/results/*"]     # yazma yalnız sonuç klasörüne


def test_idempotent():
    once, _ = configure(TEMPLATE, "CourierMemory", multi_agent=True)
    twice, _ = configure(once, "CourierMemory", multi_agent=True)
    assert twice == once


def test_single_agent_mode_reverts_to_one_runtime():
    multi, _ = configure(TEMPLATE, "CourierMemory", multi_agent=True)
    single, policy = configure(multi, "CourierMemory", multi_agent=False)
    assert policy is None and [r["name"] for r in single["runtimes"]] == ["agent"]
    assert _env(single["runtimes"][0]) == {"UNIFIED_TRACES_DESTINATION_ENABLED": "true"}
    assert "additionalPolicies" not in single["runtimes"][0]


def test_keeps_user_env_and_policies():
    t = copy.deepcopy(TEMPLATE)
    t["runtimes"][0]["envVars"] = [{"name": "CM_AGENT_MODEL_ID", "value": "global.anthropic.claude-sonnet-5"}]
    t["runtimes"][0]["additionalPolicies"] = ["arn:aws:iam::aws:policy/Example"]
    cfg, _ = configure(t, "CourierMemory", multi_agent=True)
    sup = _by_name(cfg)["agent"]
    assert _env(sup)["CM_AGENT_MODEL_ID"] == "global.anthropic.claude-sonnet-5"
    assert sup["additionalPolicies"] == ["arn:aws:iam::aws:policy/Example", POLICY_PATH]
    assert _env(_by_name(cfg)["planner"])["CM_AGENT_MODEL_ID"] == "global.anthropic.claude-sonnet-5"
