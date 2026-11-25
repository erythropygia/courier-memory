# Web dağıtımı (FastAPI + arayüzler)

Kökteki `Dockerfile` API'yi ve bütün arayüzleri tek container'da çalıştırır: `/story/` (hikaye), `/flow/` (akış),
`/legacy` (eski tek sayfa), `/docs` (API). Container AWS'de **ECS Fargate + Application Load Balancer** üzerinde koşar.

## İlk kurulum

```bash
AWS_PROFILE=<profil> AWS_REGION=us-east-1 python deploy/web/ecs_deploy.py
```

Betik image'ı derler, ECR'a yükler ve varsayılan VPC'de şunları kurar (tekrar çalıştırmak güvenlidir):

| Kaynak | Ad | Not |
|---|---|---|
| ECR | `courier-memory-web` | push'ta tarama, son 10 image |
| Güvenlik grupları | `courier-memory-web-alb`, `-task` | internetten yalnız ALB:80; container'a yalnız ALB:8000 |
| ALB + hedef grup | `courier-memory-web` | sağlık `/api/status`, boşta zaman aşımı 300 sn (canlı akışlar) |
| IAM | `courier-memory-web-exec`, `courier-memory-web-task` | container yalnız izinli modelleri çağırır (Sonnet 5, Haiku) ve `polly:SynthesizeSpeech` |
| ECS | cluster `courier-memory`, servis `courier-memory-web` | Fargate 1 vCPU / 2 GB, 1 görev, devre kesici + geri alma |

Ortam: `CM_LLM_MODE=live`, `CM_BEDROCK_CLIENT=invoke`, `CM_MODEL_ID=global.anthropic.claude-sonnet-5`,
`CM_POLLY=1` (`/api/speech`: Amazon Polly, tr-TR `Burcu` / `neural`; Polly hata verirse arayüz tarayıcı sesine düşer). Ek değişken `--env KEY=VALUE`,
ek izin `--extra-policy politika.json` (ör. DynamoDB).

## Sonraki dağıtımlar

`main`'e her push'ta GitHub Actions (`.github/workflows/ci-cd.yml`) image'ı derleyip ECR'a yükler ve ECS
servisini yeni görev tanımıyla günceller. Pipeline test koşmaz; testler push'tan önce yerelde çalıştırılır
(`PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q`). AWS kimliği OIDC ile gelir (`deploy/ci/github_oidc_setup.py`); GitHub'da secret yoktur.

## Yerelde

```bash
docker build -t courier-memory .
docker run -p 8000:8000 courier-memory                      # mock, AWS'siz
docker run -p 8000:8000 --env-file .env -v ~/.aws:/home/app/.aws:ro courier-memory   # .env'deki ayarlarla
```

App Runner bu hesapta kuruluş politikasıyla kapalı olduğu için ECS kullanılır. Kalıcı durum için `CM_STORAGE=dynamodb`.

## HTTPS (CloudFront)

```bash
AWS_PROFILE=<profil> python deploy/web/cloudfront_setup.py
```

ALB'nin önüne CloudFront koyar ve `https://<id>.cloudfront.net` adresini verir. Tarayıcı mikrofonu (sesli not, Amazon Transcribe)
yalnız HTTPS sayfada açılır; sunum ve paylaşım için bu adres kullanılır. Önbellek kapalıdır (canlı API ve akışlar), HTTP → HTTPS
yönlendirilir, kaynağa yanıt bekleme 60 sn'dir.

## Ses

- **Konuşma (Polly):** `/api/speech`, ses Burcu (neural). Rol izni `polly:SynthesizeSpeech`.
- **Sesli not (Transcribe):** `/api/transcribe`, Amazon Transcribe Streaming tr-TR; tarayıcı 16 kHz PCM gönderir. Rol izni
  `transcribe:StartStreamTranscription`. Kapalıysa ya da hata olursa arayüz tarayıcının ses tanımasına düşer.

