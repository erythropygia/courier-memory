"""agentcore.json dönüşümü (bootstrap.sh çağırır): çok ajanlı yapı ya da tek runtime.

Çok ajanlı (varsayılan):
  agent          supervisor (CM_AGENT_ROLE=supervisor); uzmanları InvokeAgentRuntime ile çağırır
  planner        Planlama Ajanı   ┐
  courier        Kurye Ajanı      ├ aynı kod (app/agent), yalnız CM_AGENT_ROLE farklı
  memory_keeper  Hafıza Ajanı     │
  analyst        Analiz Ajanı     ┘ (Athena SQL; ayrıca salt okunur Athena politikası)
Hafıza (agentMemory) CDK tarafından projedeki her runtime'a bağlanır; ayrıca bir şey yapılmaz.

Saf fonksiyon: girdiyi değiştirmez, yeni yapılandırma ve (çok ajanlıysa) supervisor IAM politikasını döndürür.

  python3 agentcore_config.py <agentcore.json> <ProjeAdı> <1|0> [hedef=default]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SUPERVISOR = "agent"                       # şablonun runtime adı; verify.sh ve `agentcore invoke --runtime agent` bunu kullanır
SPECIALISTS = ("planner", "courier", "memory_keeper", "analyst")
TRACES = ("UNIFIED_TRACES_DESTINATION_ENABLED", "true")
MANAGED_ENV = frozenset({"CM_AGENT_ROLE", "CM_RUNTIME_PREFIX", "CM_ATHENA_DATABASE", "CM_ATHENA_WORKGROUP", TRACES[0]})
POLICY_FILE = "supervisor-policy.json"     # agentcore/ klasöründe
POLICY_PATH = f"../../agentcore/{POLICY_FILE}"   # CDK bunu codeLocation'a (app/agent) göre çözer
ANALYST_POLICY_FILE = "analyst-policy.json"
ANALYST_POLICY_PATH = f"../../agentcore/{ANALYST_POLICY_FILE}"
MANAGED_POLICIES = frozenset({POLICY_PATH, ANALYST_POLICY_PATH})

# Athena (deploy/athena/athena_setup.py kurar; adlar orada da aynı)
ATHENA_DATABASE = "courier_memory"
ATHENA_WORKGROUP = "courier-memory"
ATHENA_BUCKET_PREFIX = "courier-memory-athena-"   # tam ad: courier-memory-athena-<hesap>-<bölge>


def runtime_prefix(project: str, target: str) -> str:
    """CDK runtime adı: <Proje>_<hedef>_<runtime>; önek hedefi de içerir, başka hedefin uzmanı seçilmez."""
    return f"{project}_{target}_"


def supervisor_policy(project: str, target: str) -> dict:
    # ListAgentRuntimes kaynak düzeyinde kısıtlanamaz ("*" zorunlu); çağırma yalnız bu proje + hedefin runtime'ları.
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "InvokeProjectSpecialists", "Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
         "Resource": [f"arn:aws:bedrock-agentcore:*:*:runtime/{runtime_prefix(project, target)}*"]},
        {"Sid": "FindProjectSpecialists", "Effect": "Allow", "Action": ["bedrock-agentcore:ListAgentRuntimes"], "Resource": ["*"]},
    ]}


def analyst_policy() -> dict:
    """Analiz Ajanı: Athena'da sorgu, Glue'da tablo okuma, S3'te veri okuma; yazma yalnız sorgu sonuç klasörüne."""
    bucket = f"arn:aws:s3:::{ATHENA_BUCKET_PREFIX}*"
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "RunQueries", "Effect": "Allow",
         "Action": ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
                    "athena:StopQueryExecution", "athena:GetWorkGroup"],
         "Resource": [f"arn:aws:athena:*:*:workgroup/{ATHENA_WORKGROUP}"]},
        {"Sid": "ReadCatalog", "Effect": "Allow",
         "Action": ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartition", "glue:GetPartitions"],
         "Resource": ["arn:aws:glue:*:*:catalog", f"arn:aws:glue:*:*:database/{ATHENA_DATABASE}",
                      f"arn:aws:glue:*:*:table/{ATHENA_DATABASE}/*"]},
        {"Sid": "ReadData", "Effect": "Allow", "Action": ["s3:GetObject"], "Resource": [f"{bucket}/data/*"]},
        {"Sid": "ListBucket", "Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"], "Resource": [bucket]},
        {"Sid": "WriteResults", "Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
         "Resource": [f"{bucket}/results/*"]},
    ]}


def _with_env(runtime: dict, managed: dict[str, str]) -> dict:
    user = [e for e in runtime.get("envVars") or [] if e.get("name") not in MANAGED_ENV]
    return {**runtime, "envVars": user + [{"name": k, "value": v} for k, v in managed.items()]}


def _with_policies(runtime: dict, add: tuple[str, ...] = ()) -> dict:
    """Bu betiğin yönettiği politikaları yeniden kurar; kullanıcının eklediklerini korur."""
    policies = [p for p in runtime.get("additionalPolicies") or [] if p not in MANAGED_POLICIES] + list(add)
    rest = {k: v for k, v in runtime.items() if k != "additionalPolicies"}
    return {**rest, "additionalPolicies": policies} if policies else rest


def _specialist(base: dict, role: str, traces: dict) -> dict:
    shared = {k: v for k, v in base.items() if k not in ("name", "envVars", "additionalPolicies")}
    user_policies = [p for p in base.get("additionalPolicies") or [] if p not in MANAGED_POLICIES]
    env = {"CM_AGENT_ROLE": role, **traces}
    add: tuple[str, ...] = ()
    if role == "analyst":
        env = {"CM_AGENT_ROLE": role, "CM_ATHENA_DATABASE": ATHENA_DATABASE, "CM_ATHENA_WORKGROUP": ATHENA_WORKGROUP, **traces}
        add = (ANALYST_POLICY_PATH,)
    spec = {**shared, "name": role, "envVars": base.get("envVars") or [], **({"additionalPolicies": user_policies} if user_policies else {})}
    return _with_policies(_with_env(spec, env), add=add)


def configure(cfg: dict, project: str, multi_agent: bool = True, target: str = "default") -> tuple[dict, dict | None]:
    runtimes = cfg.get("runtimes") or []
    base = next((r for r in runtimes if r.get("name") == SUPERVISOR), None)
    if base is None:
        raise ValueError(f"agentcore.json içinde '{SUPERVISOR}' runtime'ı yok (agentcore create şablonu bekleniyor)")
    others = [r for r in runtimes if r.get("name") not in (SUPERVISOR, *SPECIALISTS)]
    traces = dict([TRACES])

    if not multi_agent:
        sup = _with_policies(_with_env(base, traces))
        return {**cfg, "runtimes": [sup, *others]}, None

    prefix = runtime_prefix(project, target)
    sup = _with_policies(_with_env(base, {"CM_AGENT_ROLE": "supervisor", "CM_RUNTIME_PREFIX": prefix, **traces}), add=(POLICY_PATH,))
    specialists = [_specialist(base, role, traces) for role in SPECIALISTS]
    return {**cfg, "runtimes": [sup, *specialists, *others]}, supervisor_policy(project, target)


def _write_or_remove(path: Path, doc: dict | None) -> None:
    if doc:
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def main(argv: list[str]) -> int:
    path, project, multi = Path(argv[1]), argv[2], argv[3] != "0"
    target = argv[4] if len(argv) > 4 else "default"
    cfg, policy = configure(json.loads(path.read_text(encoding="utf-8")), project, multi_agent=multi, target=target)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_or_remove(path.parent / POLICY_FILE, policy)
    _write_or_remove(path.parent / ANALYST_POLICY_FILE, analyst_policy() if policy else None)
    names = ", ".join(r["name"] for r in cfg["runtimes"])
    print(f"  runtime'lar: {names}" + ("  (politikalar: agentcore/supervisor-policy.json, analyst-policy.json)" if policy else "  (tek ajan)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
