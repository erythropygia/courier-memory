# Courier Memory: ajanlar ve inceleyenler için kılavuz

> **In one paragraph (English summary).** Courier Memory turns the unwritten address knowledge of last-mile couriers into a shared branch memory and gives it to a courier who does not know the area, at the right moment. It is built spec-first with **Kiro** (11 specs, steering, skills, hooks, a project MCP server) and ships a **Strands** agent to **Amazon Bedrock AgentCore Runtime** with nine `@tool` functions, per-courier identity scoping enforced in code, **AgentCore Memory**, and OpenTelemetry traces to CloudWatch. The evidence table below points to the exact files.

## Nereden başlanır

| Soru | Yer |
|---|---|
| Ürün ne, kime, neden | `.kiro/steering/product.md` |
| Hangi özellik nasıl tanımlandı ve yapıldı | `.kiro/specs/<özellik>/` (`requirements.md`, `design.md`, `tasks.md`) |
| AgentCore'da ne çalışıyor | `deploy/agentcore/` + `.kiro/specs/agentcore-runtime/` |
| Parçalar arası sözleşme (API, veri biçimleri) | `docs/sozlesmeler.md` |

## Kullanılan özellikler ve kanıtı

### Kiro

| Özellik | Kanıt |
|---|---|
| **Specs** (gereksinim → tasarım → görev) | `.kiro/specs/` altında 11 spec: `dunya-simulator`, `ajanlar`, `orkestrator`, `ekonomi`, `sabah-akisi`, `api-arayuz`, `durak-kartlari`, `oz-degerlendirme-bolge`, `gercek-gun`, `akis-arayuzu`, `agentcore-runtime`. Yeni spec'lerde kabul kriterleri EARS kalıbında; görevler gereksinim numarasına bağlı |
| **Steering** (her oturumda okunan kurallar) | `.kiro/steering/`: `product`, `tech`, `structure`, `veri-kurallari`, `sunum-dili`, `agentcore`, `kiro-calisma-bicimi` (hepsi `inclusion: always`) |
| **Skills** (istenince çalışan yönergeler) | `.kiro/skills/`: `deploy-courier-memory`, `verify-deployment`, `demo-prova`, `yeni-hafiza-turu` |
| **Hooks** (kaydetmede otomasyon) | `.kiro/hooks/`: testler, veri ve KVKK denetimi, AgentCore kopyası uyarısı, sözleşme eşitleme, AgentCore şartlarını koruma |
| **MCP** | `.kiro/settings/mcp.json` → `deploy/mcp/cm_mcp_server.py` (projenin kendi sunucusu: şube hafızası, salt okunur, 5 araç). |

### Amazon Bedrock AgentCore

| Özellik | Kanıt |
|---|---|
| **Runtime** | `deploy/agentcore/runtime/main.py` (`BedrockAgentCoreApp`, tembel `_get_agent`, akış döndüren `@app.entrypoint`); iskele `agentcore create` ile, yerleştirme `deploy/agentcore/bootstrap.sh` |
| **Araçlar** (Strands `@tool`) | `deploy/agentcore/runtime/cm/tools.py`: 9 araç, deterministik alan fonksiyonlarını çağırır. İki arka uç (`cm/backend.py`): tam (`agents.Services`) ve çekirdek (`cm/core.py`, yalnız veri dosyaları; alan kodu yüklenemezse otomatik düşüş) |
| **Memory** | `deploy/agentcore/runtime/cm/memory.py`: şablonun `agentMemory` hafızası, ad alanları `actorId` ile ayrılır |
| **Kimlik sınırı** | `deploy/agentcore/runtime/cm/scope.py`: `BeforeToolCallEvent` kancası; kurye yalnız kendi verisi, müdür araçları yalnız müdür, konuk yalnız herkese açık araçlar |
| **Observability** | `UNIFIED_TRACES_DESTINATION_ENABLED=true` (`bootstrap.sh` yazar, `verify.sh` denetler); izlerde `cm.actor_role`, `cm.actor_id` |
| **Gateway**, **sohbet arayüzü (ECS Fargate)** | Sonraki adımlar: spec `agentcore-runtime` gereksinim 9–10, görev 15–16 (yapılmadı) |

### Amazon Bedrock

| Özellik | Kanıt |
|---|---|
| Claude, çıkarım profili kimliğiyle | `deploy/agentcore/runtime/cm/model.py` (AgentCore ajanı) · `agents/llm.py` `CM_BEDROCK_CLIENT=invoke` (yerel API) |
| Araç kullanan beş alan ajanı + iki yeni ajan | `agents/orchestrator.py`, `assignment.py`, `memory.py`, `briefing.py`, `harvest.py`, `review.py`, `region_agent.py`; her biri canlı yol + aynı araçlarla kurallı yedek |
| Kayıt-oynat güvencesi | `agents/llm.py`: `mock / live / record / replay` |

## Bu repoda çalışırken

- **Kod İngilizce, kullanıcıya görünen metin Türkçe.** Terim sözlüğü: `.kiro/steering/structure.md` → Adlandırma.
- **LLM karar verir, hesap araçta.** Sayı üreten her şey deterministik Python'dur (`.kiro/steering/tech.md`).
- **Kişisel veri ve kapı şifresi kaydedilmez, söylenmez.** Hafıza kişiyi değil adresi anlatır (`.kiro/steering/veri-kurallari.md`).
- **Önce spec.** Yeni özellik `.kiro/specs/<özellik>/` olmadan başlamaz; biten görev `tasks.md` içinde işaretlenir, yapılmamış iş işaretsiz kalır.
- **Test:** `PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q` (AWS gerekmez).
- **AgentCore'a giden kod repoda düzenlenir**, projedeki kopya değil: `deploy/agentcore/bootstrap.sh` → `agentcore deploy` → `deploy/agentcore/verify.sh CourierMemory --deployed`.

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
