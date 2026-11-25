"""GitHub Actions → AWS: anahtarsız (OIDC) dağıtım rolü. GitHub'da secret tutulmaz.

  AWS_PROFILE=hackathon AWS_REGION=us-east-1 python deploy/ci/github_oidc_setup.py [--repo erythropygia/courier-memory]

Kurulanlar (tekrar çalıştırmak güvenlidir):
  OIDC sağlayıcı  token.actions.githubusercontent.com (audience sts.amazonaws.com)
  IAM rolü        courier-memory-github-deploy   yalnız <repo> deposunun main dalı üstlenebilir

Rolün izinleri pipeline'ın dokunduğu kaynaklarla sınırlıdır (.github/workflows/ci-cd.yml):
  web       ECR courier-memory-web'e image yükleme, ECS courier-memory-web servisini yeni görev tanımıyla güncelleme
  quick     courier-memory-quick-bridge Lambda kodunu güncelleme
  agentcore CDK bootstrap rollerini üstlenme (CloudFormation dağıtımını onlar yapar) + AgentCore CLI'nin okuma çağrıları
"""
from __future__ import annotations

import argparse
import json
import sys

ROLE = "courier-memory-github-deploy"
OIDC_HOST = "token.actions.githubusercontent.com"


def trust_policy(account: str, repo: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Action": "sts:AssumeRoleWithWebIdentity",
        "Principal": {"Federated": f"arn:aws:iam::{account}:oidc-provider/{OIDC_HOST}"},
        "Condition": {"StringEquals": {f"{OIDC_HOST}:aud": "sts.amazonaws.com", f"{OIDC_HOST}:sub": f"repo:{repo}:ref:refs/heads/main"}}}]}


def deploy_policy(account: str, region: str) -> dict:
    a, r = account, region
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "EcrLogin", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
        {"Sid": "EcrPushWeb", "Effect": "Allow", "Resource": f"arn:aws:ecr:{r}:{a}:repository/courier-memory-web",
         "Action": ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
                    "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]},
        {"Sid": "EcsTaskDefinitions", "Effect": "Allow", "Resource": "*",
         "Action": ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]},
        {"Sid": "EcsWebService", "Effect": "Allow", "Resource": f"arn:aws:ecs:{r}:{a}:service/courier-memory/courier-memory-web",
         "Action": ["ecs:UpdateService", "ecs:DescribeServices"]},
        {"Sid": "PassWebRoles", "Effect": "Allow", "Action": "iam:PassRole",
         "Resource": [f"arn:aws:iam::{a}:role/courier-memory-web-exec", f"arn:aws:iam::{a}:role/courier-memory-web-task"],
         "Condition": {"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}},
        {"Sid": "QuickBridgeCode", "Effect": "Allow", "Resource": f"arn:aws:lambda:{r}:{a}:function:courier-memory-quick-bridge",
         "Action": ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]},
        {"Sid": "CdkBootstrapRoles", "Effect": "Allow", "Action": "sts:AssumeRole",
         "Resource": f"arn:aws:iam::{a}:role/cdk-hnb659fds-*-{a}-{r}"},
        {"Sid": "CdkBootstrapVersion", "Effect": "Allow", "Action": "ssm:GetParameter",
         "Resource": f"arn:aws:ssm:{r}:{a}:parameter/cdk-bootstrap/hnb659fds/version"},
        {"Sid": "AgentCoreCliRead", "Effect": "Allow", "Resource": "*",
         "Action": ["cloudformation:DescribeStacks", "cloudformation:DescribeStackEvents", "cloudformation:ListStackResources",
                    "bedrock-agentcore:Get*", "bedrock-agentcore:List*", "xray:GetTraceSegmentDestination", "xray:GetIndexingRules",
                    "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"]},
    ]}


def ensure_oidc(iam, account: str) -> str:
    arn = f"arn:aws:iam::{account}:oidc-provider/{OIDC_HOST}"
    if arn in [p["Arn"] for p in iam.list_open_id_connect_providers()["OpenIDConnectProviderList"]]:
        return arn
    iam.create_open_id_connect_provider(Url=f"https://{OIDC_HOST}", ClientIDList=["sts.amazonaws.com"])
    print(f"  OIDC sağlayıcı oluşturuldu: {OIDC_HOST}")
    return arn


def ensure_role(iam, account: str, region: str, repo: str) -> str:
    trust = json.dumps(trust_policy(account, repo))
    try:
        arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=ROLE, PolicyDocument=trust)
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=trust, MaxSessionDuration=3600,
                              Description=f"GitHub Actions deploy for {repo} (main)")["Role"]["Arn"]
        print(f"  IAM rolü oluşturuldu: {ROLE}")
    iam.put_role_policy(RoleName=ROLE, PolicyName="deploy", PolicyDocument=json.dumps(deploy_policy(account, region)))
    return arn


def main(argv=None) -> int:
    import boto3

    ap = argparse.ArgumentParser(description="GitHub OIDC deploy role")
    ap.add_argument("--repo", default="erythropygia/courier-memory")
    args = ap.parse_args(argv)
    s = boto3.Session()
    region, account = s.region_name or "us-east-1", s.client("sts").get_caller_identity()["Account"]
    iam = s.client("iam")
    ensure_oidc(iam, account)
    print(f"Hazır. Workflow'daki AWS_ROLE_ARN: {ensure_role(iam, account, region, args.repo)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
