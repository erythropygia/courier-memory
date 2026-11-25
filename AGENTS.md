# Courier Memory: ajanlar ve inceleyenler için kılavuz

> **In one paragraph (English summary).** Courier Memory turns the unwritten address knowledge of last-mile couriers into a shared branch memory and gives it to a courier who does not know the area, at the right moment. It is built spec-first with **Kiro** (17 specs, steering, skills, hooks, two MCP servers). Twelve agents run on AWS: seven domain agents (orchestrator, assignment, memory, briefing, harvest, review, region) inside the web app on **Amazon ECS Fargate**, and five agents on **Amazon Bedrock AgentCore Runtime** (a Supervisor and four specialists that call the same domain agents as tools), with identity scoping enforced in code, **AgentCore Memory**, a visible agent-to-agent trace, and **AgentCore Gateway** for **Amazon Quick** and Kiro over MCP. State lives in **Amazon DynamoDB**, history in **Amazon Athena**, voice runs on **Amazon Transcribe** and **Amazon Polly**, and every push to `main` deploys through GitHub Actions with OIDC. The evidence tables below point to the exact files.

## Canlı sistem

`https://d21h79c269fwie.cloudfront.net` (us-east-1, etkinlik hesabı; etkinlik süresince açık)

| Adres | Ne |
|---|---|
| `/flow/?sunum=1` | Sunum ekranı: **Günü planla** (7 alan ajanı, 8 adım) ve **AgentCore zinciri** (Supervisor → uzman → araç, 6 adım) |
| `/flow/` | Aynı zinciri izleyen ekran (QR buraya açılır) |
| `/story/` · `/demo/` · `/legacy` · `/docs` | Hikaye (8 sahne) · QR demo izi · ayrıntı ekranları · API |

## Nereden başlanır

| Soru | Yer |
|---|---|
| Ürün ne, kime, neden | `.kiro/steering/product.md` |
| Mimari (ajanlar ve AWS) | `docs/mimari/mimari-akis.gif`, `docs/mimari/aws-altyapi.gif` |
| Hangi özellik nasıl tanımlandı ve yapıldı | `.kiro/specs/<özellik>/` (`requirements.md`, `design.md`, `tasks.md`) |
| AgentCore'da ne çalışıyor | `deploy/agentcore/` + `.kiro/specs/agentcore-runtime/`, `agentcore-zinciri/` |
| AWS'ye nasıl dağıtılıyor | `deploy/web/`, `deploy/quick/`, `deploy/athena/`, `deploy/dynamodb/`, `.github/workflows/ci-cd.yml` + `.kiro/specs/aws-dagitim/` |
| Parçalar arası sözleşme (API, veri biçimleri, canlı zincir olayları) | `docs/sozlesmeler.md` |

## Mimari: 12 ajan

```
Web uygulaması (ECS Fargate)              Amazon Bedrock AgentCore Runtime
 Orkestratör → Atama → hafızalı rota       Supervisor ── ask_planner ──► Planlama → plan_day, morning_review, region_report
  → Acil Durum Kapısı → Brifing                       ├─ ask_courier_agent ► Kurye  → courier_briefing, stop_cards, approaching_stop
  → Hafıza → Hasat → Değerlendirme → Bölge            ├─ ask_memory_keeper ► Hafıza → leave_note, harvest_questions, branch_memory_summary
  (7 alan ajanı, canlı Claude)                        └─ ask_analyst ──────► Analiz → query_history (Athena SQL)
                                            Uzmanların araçları aynı 7 alan ajanını çağırır; kimlik istekten gelir.
            └──────────── ortak durum: DynamoDB `courier-memory` ────────────┘
```

## Kullanılan özellikler ve kanıtı

### Kiro

| Özellik | Kanıt |
|---|---|
| **Specs** (gereksinim → tasarım → görev) | `.kiro/specs/` altında 17 spec: `dunya-simulator`, `ajanlar`, `orkestrator`, `ekonomi`, `sabah-akisi`, `api-arayuz`, `durak-kartlari`, `oz-degerlendirme-bolge`, `gercek-gun`, `akis-arayuzu`, `canli-akis`, `demo-izi`, `agentcore-runtime`, `agentcore-zinciri`, `athena-analiz`, `quick-koprusu`, `aws-dagitim`. Kabul kriterleri EARS kalıbında; görevler gereksinim numarasına bağlı |
| **Steering** (her oturumda okunan kurallar) | `.kiro/steering/`: `product`, `tech`, `structure`, `veri-kurallari`, `sunum-dili`, `agentcore`, `kiro-calisma-bicimi`, `aws-agent-toolkit` |
| **Skills** (istenince çalışan yönergeler) | `.kiro/skills/`: `deploy-courier-memory` (beş runtime, çok ajanlı sınama), `verify-deployment`, `demo-prova`, `yeni-hafiza-turu` |
| **Hooks** (kaydetmede otomasyon) | `.kiro/hooks/`: testler, veri ve KVKK denetimi, AgentCore kopyası uyarısı, sözleşme eşitleme, AgentCore şartlarını koruma (beş runtime, politikalar, kimlik) |
| **MCP** | `.kiro/settings/mcp.json`: `courier-memory` → `deploy/mcp/cm_mcp_server.py` (yerel, salt okunur, 5 araç) · `courier-memory-live` → `deploy/quick/kiro_mcp_proxy.py` (dağıtılmış ajanlara AgentCore Gateway üzerinden; kimlik bilgisi `.env`'den) |

### Amazon Bedrock AgentCore

| Özellik | Kanıt |
|---|---|
| **Runtime** (5 ajan, tek kod paketi) | `deploy/agentcore/runtime/main.py`; rol `CM_AGENT_ROLE` ile `cm/roles.py`; runtime tanımları ve en az yetkili politikalar `deploy/agentcore/agentcore_config.py`; yerleştirme `bootstrap.sh` |
| **Çok ajanlı yönlendirme** | `cm/roles.py` (`ask_*` araçları), `cm/delegate.py` (`InvokeAgentRuntime`, ARN adla bulunur, yeniden deneme yok) |
| **Araçlar** (Strands `@tool`) | `cm/tools.py`: 10 alan aracı (deterministik alan fonksiyonları) · `cm/athena.py`: `query_history` (tek `SELECT`, en çok 200 satır) |
| **Kimlik sınırı** | `cm/scope.py` (`BeforeToolCallEvent`): kurye yalnız kendi verisi, müdür araçları yalnız müdür; Supervisor'da kimlik kapanıştan gelir, model değiştiremez |
| **Memory** | `cm/memory.py`: `agentMemory`, ad alanları `actorId` ile ayrılır |
| **Observability** | `UNIFIED_TRACES_DESTINATION_ENABLED=true` + `cm/trace.py`: `cm_trace` olayları (araç çağrısı, sonuç, yönlendirme, ret) uzmandan Supervisor'a akar; sözleşme `deploy/agentcore/README.md` |
| **Gateway** | `deploy/quick/`: AgentCore Gateway (MCP, Cognito JWT) → Lambda → Supervisor; Amazon Quick ve Kiro buradan bağlanır |

### Amazon Bedrock

| Özellik | Kanıt |
|---|---|
| Claude (Sonnet 5), çıkarım profili kimliğiyle | `deploy/agentcore/runtime/cm/model.py` · `agents/llm.py` (`CM_BEDROCK_CLIENT=invoke`) |
| Araç kullanan yedi alan ajanı | `agents/orchestrator.py`, `assignment.py`, `memory.py`, `briefing.py`, `harvest.py`, `review.py`, `region_agent.py`; her biri canlı yol + aynı araçlarla kurallı yedek |
| Canlı zincir | `api/live.py` (8 adım, SSE) · `api/agentcore_chain.py` (AgentCore zinciri, 6 adım) |
| Kayıt-oynat güvencesi | `agents/llm.py`: `mock / live / record / replay` |

### Diğer AWS servisleri

| Servis | Kanıt |
|---|---|
| CloudFront → ALB → ECS Fargate, ECR | `deploy/web/ecs_deploy.py`, `cloudfront_setup.py`, kökteki `Dockerfile`; ALB yalnız CloudFront'a açık |
| DynamoDB (ortak durum: hafıza, akış, kullanım) | `agents/storage/` (`CM_STORAGE=dynamodb`), `deploy/dynamodb/create_table.py` |
| S3 + Glue + Athena (geçmiş veri, salt okunur SQL) | `deploy/athena/athena_setup.py`, `deploy/agentcore/runtime/cm/athena.py` |
| Transcribe (sesli not) · Polly (kartı okur) | `api/transcribe.py`, `api/transcribe_client.py`, `ui/story/js/listen.js` · `api/main.py` `/api/speech` |
| Amazon Quick + Cognito + Lambda | `deploy/quick/quick_bridge_setup.py`, `bridge_lambda.py` |
| IAM en az yetki | `deploy/agentcore/agentcore_config.py`, `deploy/web/ecs_deploy.py`, `deploy/ci/github_oidc_setup.py` |
| CI/CD (GitHub Actions, OIDC, secret yok) | `.github/workflows/ci-cd.yml`: `main`'e push'ta değişen parça dağıtılır (web, AgentCore, Quick köprüsü) |

## Bu repoda çalışırken

- **Kod İngilizce, kullanıcıya görünen metin Türkçe.** Terim sözlüğü: `.kiro/steering/structure.md` → Adlandırma.
- **LLM karar verir, hesap araçta.** Sayı üreten her şey deterministik Python'dur (`.kiro/steering/tech.md`).
- **Kişisel veri ve kapı şifresi kaydedilmez, söylenmez.** Hafıza kişiyi değil adresi anlatır (`.kiro/steering/veri-kurallari.md`).
- **Önce spec.** Yeni özellik `.kiro/specs/<özellik>/` olmadan başlamaz; biten görev `tasks.md` içinde işaretlenir, yapılmamış iş işaretsiz kalır.
- **Test:** `PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q` (AWS gerekmez). Pipeline test koşmaz; testler push'tan önce yerelde.
- **Dağıtım:** `main`'e push CI ile dağıtır. Elle: AgentCore `deploy/agentcore/bootstrap.sh` → `agentcore deploy` → `verify.sh CourierMemory --deployed`; web `deploy/web/ecs_deploy.py`. Ayarlar ve kimlik bilgileri `.env` (şablon `.env.example`).

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- For any AWS task or question — building, configuring, migrating, debugging, or operating a service, writing SDK code, authoring CDK/CloudFormation, or answering how a service works — first call `aws___search_documentation` with topic `agent_skills` and load the matching skill with `aws___retrieve_skill`. Do this even when you believe you know the answer: skills carry current service behavior that your training may not. Prefer the skill's guidance over general knowledge. Skip it only for work that does not involve AWS.

### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion

<!-- END AWS Agent Toolkit rules -->
