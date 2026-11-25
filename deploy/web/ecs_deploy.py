"""Web uygulamasını (FastAPI + arayüzler, kökteki Dockerfile) Amazon ECS Fargate + Application Load Balancer'a dağıtır.

  AWS_PROFILE=hackathon AWS_REGION=us-east-1 python deploy/web/ecs_deploy.py              # derle, yükle, dağıt
  python deploy/web/ecs_deploy.py --skip-build --image-tag <tag>                           # CI: image ECR'da hazır

Kurulanlar (varsayılan VPC'de; tekrar çalıştırmak güvenlidir):
  ECR deposu       courier-memory-web             push'ta tarama, son 10 image
  Güvenlik grubu   courier-memory-web-alb         internetten 80
  Güvenlik grubu   courier-memory-web-task        yalnız ALB'den 8000
  ALB + hedef grup courier-memory-web             HTTP 80 → container 8000, sağlık /api/status, boşta zaman aşımı 300 sn
  IAM rolleri      courier-memory-web-exec (image çekme, log) · courier-memory-web-task (container kimliği: izinli modeller, Polly)
  ECS              cluster courier-memory · servis courier-memory-web (Fargate, 1 vCPU / 2 GB, 1 görev)

Model: Sonnet 5 (demo/test için Opus kullanılmaz). Varsayılan: Polly (Burcu, neural) ve DynamoDB (courier-memory; yalnız bu tabloya izin).
Ek izin için --extra-policy, ek ortam için --env (aynı adlı varsayılanı ezer; CM_STORAGE=file ile tablo kapatılır).
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

NAME = "courier-memory-web"
CLUSTER = "courier-memory"
EXEC_ROLE, TASK_ROLE = "courier-memory-web-exec", "courier-memory-web-task"
LOG_GROUP = "/ecs/courier-memory-web"
PORT = 8000
ROOT = Path(__file__).resolve().parents[2]
MODELS = ("anthropic.claude-sonnet-5", "anthropic.claude-haiku-4-5-20251001-v1:0")
ENV = {"CM_LLM_MODE": "live", "CM_BEDROCK_CLIENT": "invoke", "CM_MODEL_ID": "global.anthropic.claude-sonnet-5",
       "CM_AUTO_CACHE": "1", "CM_RUN_DIR": "data/demo_run",
       "CM_POLLY": "1", "CM_POLLY_VOICE": "Burcu", "CM_POLLY_ENGINE": "neural",  # /api/speech: Polly tr-TR neural ses
       "CM_STORAGE": "dynamodb", "CM_DYNAMODB_TABLE": "courier-memory", "CM_DYNAMODB_SYNC_SECONDS": "1"}  # ortak durum tablosu
# deploy/dynamodb/create_table.py APP_ACTIONS ile aynı (tablo: deploy/dynamodb/create_table.py ile kurulur)
STORAGE_ACTIONS = ("dynamodb:GetItem", "dynamodb:Query", "dynamodb:BatchGetItem",
                   "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem")


# ------------------------------------------------------------------ IAM
def _role(iam, name, service, managed=(), inline=None):
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]}
    try:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Description="Courier Memory web")["Role"]["Arn"]
        print(f"  IAM rolü oluşturuldu: {name}")
    for m in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=m)
    for pname, doc in (inline or {}).items():
        iam.put_role_policy(RoleName=name, PolicyName=pname, PolicyDocument=json.dumps(doc))
    return arn


def bedrock_policy() -> dict:
    profiles = [f"arn:aws:bedrock:*:*:inference-profile/{p}.{m}" for m in MODELS for p in ("global", "us")]
    models = [f"arn:aws:bedrock:*::foundation-model/{m}" for m in MODELS]
    return {"Version": "2012-10-17", "Statement": [{"Sid": "InvokeAllowedModels", "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], "Resource": profiles + models}]}


def polly_policy() -> dict:
    # polly:SynthesizeSpeech yalnız lexicon ARN'i ile kısıtlanabilir; lexicon'suz istek bir kaynağa bağlanmaz,
    # bu yüzden Resource "*" zorunludur (Polly IAM örnekleri). Yalnız bu tek eylem verilir.
    return {"Version": "2012-10-17", "Statement": [{"Sid": "SynthesizeSpeech", "Effect": "Allow",
            "Action": ["polly:SynthesizeSpeech"], "Resource": "*"}]}


def storage_policy(region: str, account: str, table: str) -> dict:
    """Yalnız bu tablo; tablo silme ve tarama yok."""
    return {"Version": "2012-10-17", "Statement": [{"Sid": "CourierMemoryTable", "Effect": "Allow", "Action": list(STORAGE_ACTIONS),
            "Resource": [f"arn:aws:dynamodb:{region}:{account}:table/{table}"]}]}


# ------------------------------------------------------------------ image
def ensure_repo(ecr) -> str:
    try:
        uri = ecr.describe_repositories(repositoryNames=[NAME])["repositories"][0]["repositoryUri"]
    except ecr.exceptions.RepositoryNotFoundException:
        uri = ecr.create_repository(repositoryName=NAME, imageScanningConfiguration={"scanOnPush": True})["repository"]["repositoryUri"]
        print(f"  ECR deposu oluşturuldu: {NAME}")
    ecr.put_lifecycle_policy(repositoryName=NAME, lifecyclePolicyText=json.dumps({"rules": [{
        "rulePriority": 1, "description": "son 10 image", "action": {"type": "expire"},
        "selection": {"tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 10}}]}))
    return uri


def build_and_push(ecr, uri: str, tag: str) -> None:
    auth = ecr.get_authorization_token()["authorizationData"][0]
    user, pwd = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    subprocess.run(["docker", "login", "-u", user, "--password-stdin", auth["proxyEndpoint"]], input=pwd.encode(), check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", f"{uri}:{tag}", "-t", f"{uri}:latest", str(ROOT)], check=True)
    for t in (tag, "latest"):
        subprocess.run(["docker", "push", f"{uri}:{t}"], check=True, stdout=subprocess.DEVNULL)
    print(f"  image yüklendi: {uri}:{tag}")


# ------------------------------------------------------------------ ağ
def _sg(ec2, vpc, name, desc, ingress):
    found = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [name]}, {"Name": "vpc-id", "Values": [vpc]}])["SecurityGroups"]
    sg = found[0]["GroupId"] if found else ec2.create_security_group(GroupName=name, Description=desc, VpcId=vpc)["GroupId"]
    try:
        ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[ingress])
    except ec2.exceptions.ClientError as e:
        if "InvalidPermission.Duplicate" not in str(e):
            raise
    return sg


def network(ec2) -> tuple[str, list[str], str, str]:
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    subnets = [s["SubnetId"] for s in ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                                                    {"Name": "default-for-az", "Values": ["true"]}])["Subnets"]]
    alb_sg = _sg(ec2, vpc, f"{NAME}-alb", "Courier Memory web ALB",
                 {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]})
    task_sg = _sg(ec2, vpc, f"{NAME}-task", "Courier Memory web tasks",
                  {"IpProtocol": "tcp", "FromPort": PORT, "ToPort": PORT, "UserIdGroupPairs": [{"GroupId": alb_sg}]})
    return vpc, subnets, alb_sg, task_sg


def load_balancer(elb, vpc, subnets, alb_sg) -> tuple[str, str]:
    try:
        lb = elb.describe_load_balancers(Names=[NAME])["LoadBalancers"][0]
    except elb.exceptions.LoadBalancerNotFoundException:
        lb = elb.create_load_balancer(Name=NAME, Subnets=subnets[:3], SecurityGroups=[alb_sg], Scheme="internet-facing",
                                      Type="application")["LoadBalancers"][0]
        print(f"  ALB oluşturuldu: {lb['DNSName']}")
    elb.modify_load_balancer_attributes(LoadBalancerArn=lb["LoadBalancerArn"],
                                        Attributes=[{"Key": "idle_timeout.timeout_seconds", "Value": "300"}])
    try:
        tg = elb.describe_target_groups(Names=[NAME])["TargetGroups"][0]["TargetGroupArn"]
    except elb.exceptions.TargetGroupNotFoundException:
        tg = elb.create_target_group(Name=NAME, Protocol="HTTP", Port=PORT, VpcId=vpc, TargetType="ip", HealthCheckPath="/api/status",
                                     HealthCheckIntervalSeconds=15, HealthyThresholdCount=2, UnhealthyThresholdCount=5)["TargetGroups"][0]["TargetGroupArn"]
    elb.modify_target_group_attributes(TargetGroupArn=tg, Attributes=[{"Key": "deregistration_delay.timeout_seconds", "Value": "15"}])
    if not elb.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])["Listeners"]:
        elb.create_listener(LoadBalancerArn=lb["LoadBalancerArn"], Protocol="HTTP", Port=80,
                            DefaultActions=[{"Type": "forward", "TargetGroupArn": tg}])
    return lb["DNSName"], tg


# ------------------------------------------------------------------ ECS
def task_definition(ecs, logs, image, exec_role, task_role, env, region) -> str:
    try:
        logs.create_log_group(logGroupName=LOG_GROUP)
        logs.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=14)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    container = {"name": "web", "image": image, "essential": True, "portMappings": [{"containerPort": PORT, "protocol": "tcp"}],
                 "environment": [{"name": k, "value": v} for k, v in env.items()],
                 "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-group": LOG_GROUP, "awslogs-region": region,
                                                                           "awslogs-stream-prefix": "web"}}}
    return ecs.register_task_definition(family=NAME, networkMode="awsvpc", requiresCompatibilities=["FARGATE"], cpu="1024", memory="2048",
                                        executionRoleArn=exec_role, taskRoleArn=task_role,
                                        runtimePlatform={"cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX"},
                                        containerDefinitions=[container])["taskDefinition"]["taskDefinitionArn"]


def service(ecs, td, tg, subnets, task_sg) -> None:
    ecs.create_cluster(clusterName=CLUSTER)
    existing = [s for s in ecs.describe_services(cluster=CLUSTER, services=[NAME])["services"] if s["status"] == "ACTIVE"]
    if existing:
        ecs.update_service(cluster=CLUSTER, service=NAME, taskDefinition=td, forceNewDeployment=True)
    else:
        ecs.create_service(cluster=CLUSTER, serviceName=NAME, taskDefinition=td, desiredCount=1, launchType="FARGATE",
                           loadBalancers=[{"targetGroupArn": tg, "containerName": "web", "containerPort": PORT}],
                           healthCheckGracePeriodSeconds=120,
                           deploymentConfiguration={"minimumHealthyPercent": 0, "maximumPercent": 100,
                                                    "deploymentCircuitBreaker": {"enable": True, "rollback": True}},
                           networkConfiguration={"awsvpcConfiguration": {"subnets": subnets[:3], "securityGroups": [task_sg],
                                                                         "assignPublicIp": "ENABLED"}})
        print(f"  ECS servisi oluşturuldu: {NAME}")
    ecs.get_waiter("services_stable").wait(cluster=CLUSTER, services=[NAME], WaiterConfig={"Delay": 15, "MaxAttempts": 60})


def main(argv=None) -> int:
    import boto3

    ap = argparse.ArgumentParser(description="Courier Memory web → ECS Fargate + ALB")
    ap.add_argument("--image-tag", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--skip-build", action="store_true", help="image ECR'da hazır (CI)")
    ap.add_argument("--extra-policy", action="append", default=[], help="container rolüne eklenecek politika JSON dosyası")
    ap.add_argument("--env", action="append", default=[], help="ek ortam değişkeni KEY=VALUE")
    args = ap.parse_args(argv)

    s = boto3.Session()
    region = s.region_name or "us-east-1"
    c = lambda n: s.client(n, region_name=region)  # noqa: E731
    print(f"==> ECS dağıtımı: bölge {region}, servis {NAME}")
    uri = ensure_repo(c("ecr"))
    if not args.skip_build:
        build_and_push(c("ecr"), uri, args.image_tag)
    iam = s.client("iam")
    exec_role = _role(iam, EXEC_ROLE, "ecs-tasks.amazonaws.com",
                      managed=("arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",))
    extra = {Path(p).stem: json.loads(Path(p).read_text(encoding="utf-8")) for p in args.extra_policy}
    env = {**ENV, "AWS_REGION": region, **dict(e.split("=", 1) for e in args.env)}
    account = s.client("sts").get_caller_identity()["Account"]
    storage = ({f"dynamodb-{env['CM_DYNAMODB_TABLE']}": storage_policy(region, account, env["CM_DYNAMODB_TABLE"])}
               if env.get("CM_STORAGE") == "dynamodb" else {})
    task_role = _role(iam, TASK_ROLE, "ecs-tasks.amazonaws.com", inline={"bedrock-allowed-models": bedrock_policy(),
                                                                         "polly-synthesize-speech": polly_policy(), **storage, **extra})
    vpc, subnets, alb_sg, task_sg = network(c("ec2"))
    dns, tg = load_balancer(c("elbv2"), vpc, subnets, alb_sg)
    time.sleep(10)                                   # yeni rollerin yayılması
    td = task_definition(c("ecs"), c("logs"), f"{uri}:{args.image_tag}", exec_role, task_role, env, region)
    service(c("ecs"), td, tg, subnets, task_sg)
    print(f"Hazır: http://{dns}  (story: /story/  akış: /flow/  eski: /legacy  API: /docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
