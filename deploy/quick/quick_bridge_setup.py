"""Amazon Quick köprüsünü kurar: Quick (MCP connector) → AgentCore Gateway → Lambda → Courier Memory supervisor.

  AWS_PROFILE=hackathon AWS_REGION=us-east-1 python deploy/quick/quick_bridge_setup.py [--test]

Kurulanlar (tekrar çalıştırmak güvenlidir):
  IAM rolü    courier-memory-quick-lambda    yalnız supervisor runtime'ını çağırır
  Lambda      courier-memory-quick-bridge    bridge_lambda.py
  Cognito     courier-memory-quick           makineler arası anahtar (client credentials, kapsam courier-memory/invoke)
  IAM rolü    courier-memory-quick-gateway   yalnız bu Lambda'yı çağırır
  Gateway     courier-memory-quick           MCP, CUSTOM_JWT (yalnız bu Cognito istemcisi); hedef: ask_courier_memory

Quick'e girilecek değerler ~/.courier-memory/quick-bridge.json dosyasına yazılır (Client Secret içerir; repoya koymayın).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

NAME = "courier-memory-quick"
LAMBDA_NAME = "courier-memory-quick-bridge"
LAMBDA_ROLE = "courier-memory-quick-lambda"
GATEWAY_ROLE = "courier-memory-quick-gateway"
TARGET = "courier-memory"
SCOPE_ID, SCOPE = "courier-memory", "invoke"
OUT = Path.home() / ".courier-memory" / "quick-bridge.json"
HERE = Path(__file__).resolve().parent

TOOL_SCHEMA = [{
    "name": "ask_courier_memory",
    "description": ("Courier Memory kargo şubesi asistanına soru sorar (Türkçe). Beş ajanlı sistem: günün planı ve kapasite, "
                    "sabah değerlendirmesi, bölge raporu, kurye brifingi ve durak kartları, adres hafızası ve hasat soruları, "
                    "40 günlük geçmiş veriden SQL analiz (başarısız teslim, nedenler, yapılar arası fark). "
                    "Ask the Courier Memory branch assistant (parcel delivery planning, courier briefings, address memory, analytics)."),
    "inputSchema": {"type": "object", "required": ["question"], "properties": {
        "question": {"type": "string", "description": "Kullanıcının sorusu, eksiksiz ve tek parça (Türkçe olabilir)."},
        "day": {"type": "integer", "description": "İsteğe bağlı simülasyon günü (20-39); verilmezse demo günü."}}},
}]


def _wait(fn, ok, what, tries=60, delay=5):
    for _ in range(tries):
        v = fn()
        if ok(v):
            return v
        time.sleep(delay)
    raise TimeoutError(what)


# ------------------------------------------------------------------ IAM
def _role(iam, name, trust, inline_name, inline, managed=()):
    try:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
                              Description="Courier Memory Quick bridge")["Role"]["Arn"]
        print(f"  IAM rolü oluşturuldu: {name}")
    iam.put_role_policy(RoleName=name, PolicyName=inline_name, PolicyDocument=json.dumps(inline))
    for m in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=m)
    return arn


def lambda_role(iam, supervisor_arn):
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                      "Action": "sts:AssumeRole"}]}
    inline = {"Version": "2012-10-17", "Statement": [{"Sid": "InvokeSupervisorOnly", "Effect": "Allow",
                                                       "Action": "bedrock-agentcore:InvokeAgentRuntime",
                                                       "Resource": [supervisor_arn, f"{supervisor_arn}/runtime-endpoint/*"]}]}
    return _role(iam, LAMBDA_ROLE, trust, "invoke-supervisor", inline,
                 managed=("arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",))


def gateway_role(iam, account, lambda_arn):
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                                                      "Action": "sts:AssumeRole",
                                                      "Condition": {"StringEquals": {"aws:SourceAccount": account}}}]}
    inline = {"Version": "2012-10-17", "Statement": [{"Sid": "InvokeBridgeOnly", "Effect": "Allow",
                                                       "Action": "lambda:InvokeFunction", "Resource": lambda_arn}]}
    return _role(iam, GATEWAY_ROLE, trust, "invoke-bridge-lambda", inline)


# ------------------------------------------------------------------ Lambda
def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "bridge_lambda.py", "bridge_lambda.py")
    return buf.getvalue()


def bridge_lambda(lam, role_arn, supervisor_arn):
    env = {"Variables": {"SUPERVISOR_RUNTIME_ARN": supervisor_arn, "QUICK_ACTOR_ID": "MUDUR-QUICK"}}
    cfg = dict(Role=role_arn, Handler="bridge_lambda.handler", Runtime="python3.13", Timeout=280, MemorySize=256,
               Environment=env, Description="Amazon Quick -> Courier Memory supervisor")
    try:
        lam.get_function(FunctionName=LAMBDA_NAME)
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=_zip())
        lam.get_waiter("function_updated_v2").wait(FunctionName=LAMBDA_NAME)
        arn = lam.update_function_configuration(FunctionName=LAMBDA_NAME, **cfg)["FunctionArn"]
    except lam.exceptions.ResourceNotFoundException:
        for attempt in range(10):                   # yeni rolün yayılması birkaç saniye sürer
            try:
                arn = lam.create_function(FunctionName=LAMBDA_NAME, Code={"ZipFile": _zip()}, **cfg)["FunctionArn"]
                break
            except lam.exceptions.InvalidParameterValueException:
                if attempt == 9:
                    raise
                time.sleep(6)
        print(f"  Lambda oluşturuldu: {LAMBDA_NAME}")
    lam.get_waiter("function_updated_v2").wait(FunctionName=LAMBDA_NAME)
    return arn


# ------------------------------------------------------------------ Cognito
def cognito(idp, region, account):
    pools = [p for p in idp.list_user_pools(MaxResults=60)["UserPools"] if p["Name"] == NAME]
    pool_id = pools[0]["Id"] if pools else idp.create_user_pool(PoolName=NAME)["UserPool"]["Id"]
    domain = f"{NAME}-{account}"
    if not idp.describe_user_pool_domain(Domain=domain).get("DomainDescription", {}).get("UserPoolId"):
        idp.create_user_pool_domain(Domain=domain, UserPoolId=pool_id)
    try:
        idp.describe_resource_server(UserPoolId=pool_id, Identifier=SCOPE_ID)
    except idp.exceptions.ResourceNotFoundException:
        idp.create_resource_server(UserPoolId=pool_id, Identifier=SCOPE_ID, Name="Courier Memory",
                                   Scopes=[{"ScopeName": SCOPE, "ScopeDescription": "Courier Memory ajanını çağır"}])
    clients = [c for c in idp.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)["UserPoolClients"] if c["ClientName"] == "quick"]
    if clients:
        client = idp.describe_user_pool_client(UserPoolId=pool_id, ClientId=clients[0]["ClientId"])["UserPoolClient"]
    else:
        client = idp.create_user_pool_client(UserPoolId=pool_id, ClientName="quick", GenerateSecret=True,
                                             AllowedOAuthFlows=["client_credentials"], AllowedOAuthFlowsUserPoolClient=True,
                                             AllowedOAuthScopes=[f"{SCOPE_ID}/{SCOPE}"], SupportedIdentityProviders=["COGNITO"],
                                             AccessTokenValidity=60, TokenValidityUnits={"AccessToken": "minutes"})["UserPoolClient"]
        print(f"  Cognito istemcisi oluşturuldu: {pool_id}")
    return {"pool_id": pool_id, "client_id": client["ClientId"], "client_secret": client["ClientSecret"],
            "token_url": f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token",
            "discovery_url": f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"}


# ------------------------------------------------------------------ Gateway
def gateway(ctl, role_arn, cog):
    auth = {"customJWTAuthorizer": {"discoveryUrl": cog["discovery_url"], "allowedClients": [cog["client_id"]]}}
    found = [g for g in ctl.list_gateways(maxResults=100).get("items", []) if g["name"] == NAME]
    if found:
        gid = found[0]["gatewayId"]
    else:
        gid = ctl.create_gateway(name=NAME, roleArn=role_arn, protocolType="MCP", authorizerType="CUSTOM_JWT",
                                 authorizerConfiguration=auth, description="Amazon Quick -> Courier Memory")["gatewayId"]
        print(f"  Gateway oluşturuldu: {gid}")
    g = _wait(lambda: ctl.get_gateway(gatewayIdentifier=gid), lambda g: g["status"] in ("READY", "FAILED"), "gateway READY")
    if g["status"] != "READY":
        raise RuntimeError(f"Gateway {g['status']}: {g.get('statusReasons')}")
    return g


def gateway_target(ctl, gid, lambda_arn):
    cfg = {"mcp": {"lambda": {"lambdaArn": lambda_arn, "toolSchema": {"inlinePayload": TOOL_SCHEMA}}}}
    creds = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    found = [t for t in ctl.list_gateway_targets(gatewayIdentifier=gid, maxResults=100).get("items", []) if t["name"] == TARGET]
    if found:
        tid = found[0]["targetId"]
        ctl.update_gateway_target(gatewayIdentifier=gid, targetId=tid, name=TARGET, targetConfiguration=cfg,
                                  credentialProviderConfigurations=creds)
    else:
        tid = ctl.create_gateway_target(gatewayIdentifier=gid, name=TARGET, targetConfiguration=cfg,
                                        credentialProviderConfigurations=creds)["targetId"]
        print(f"  Gateway hedefi oluşturuldu: {TARGET}")
    t = _wait(lambda: ctl.get_gateway_target(gatewayIdentifier=gid, targetId=tid),
              lambda t: t["status"] in ("READY", "FAILED", "UPDATE_UNSUCCESSFUL"), "target READY")
    if t["status"] != "READY":
        raise RuntimeError(f"Hedef {t['status']}: {t.get('statusReasons')}")


# ------------------------------------------------------------------ test
def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - yalnız kendi https uç noktalarımız
        return r.read().decode("utf-8")


def smoke_test(out):
    tok = json.loads(_post(out["token_url"], urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": f"{SCOPE_ID}/{SCOPE}"}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded",
         "Authorization": "Basic " + base64.b64encode(f"{out['client_id']}:{out['client_secret']}".encode()).decode()}))
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "Authorization": f"Bearer {tok['access_token']}"}
    tools = json.loads(_post(out["mcp_url"], json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(), h))
    print("  tools/list:", [t["name"] for t in tools["result"]["tools"]])
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": tools["result"]["tools"][0]["name"], "arguments": {"question": "Şube hafızasının özetini iki cümleyle ver."}}}
    res = json.loads(_post(out["mcp_url"], json.dumps(call).encode(), h))
    print("  tools/call:", json.dumps(res.get("result") or res.get("error"), ensure_ascii=False)[:600])


def main(argv=None) -> int:
    import boto3

    ap = argparse.ArgumentParser(description="Amazon Quick köprüsü")
    ap.add_argument("--runtime-name", default="CourierMemory_default_agent")
    ap.add_argument("--test", action="store_true", help="kurulumdan sonra token alıp araç listesini ve bir soruyu dener")
    args = ap.parse_args(argv)

    s = boto3.Session()
    region = s.region_name or "us-east-1"
    account = s.client("sts").get_caller_identity()["Account"]
    ctl = s.client("bedrock-agentcore-control", region_name=region)
    sup = [r for r in ctl.list_agent_runtimes(maxResults=100)["agentRuntimes"] if r["agentRuntimeName"] == args.runtime_name]
    if not sup:
        sys.exit(f"Supervisor runtime bulunamadı: {args.runtime_name} (önce agentcore deploy)")
    print(f"==> Quick köprüsü: hesap {account}, bölge {region}, supervisor {args.runtime_name}")

    iam, lam = s.client("iam"), s.client("lambda", region_name=region)
    fn_arn = bridge_lambda(lam, lambda_role(iam, sup[0]["agentRuntimeArn"]), sup[0]["agentRuntimeArn"])
    cog = cognito(s.client("cognito-idp", region_name=region), region, account)
    gw_role = gateway_role(iam, account, fn_arn)
    time.sleep(10)                                   # yeni rol izninin yayılması
    g = gateway(ctl, gw_role, cog)
    gateway_target(ctl, g["gatewayId"], fn_arn)

    out = {"mcp_url": g["gatewayUrl"], "client_id": cog["client_id"], "client_secret": cog["client_secret"],
           "token_url": cog["token_url"], "scope": f"{SCOPE_ID}/{SCOPE}", "gateway_id": g["gatewayId"], "lambda": fn_arn}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Hazır. Quick'e girilecek değerler: {OUT}  (Client Secret içerir)")
    print(f"  MCP adresi: {out['mcp_url']}\n  Token URL : {out['token_url']}\n  Client ID : {out['client_id']}")
    if args.test:
        smoke_test(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
