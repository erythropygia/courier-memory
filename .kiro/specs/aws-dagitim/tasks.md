# Uygulama planı: AWS'de web uygulaması ve kalıcı durum

1 repoda. 2–5 web dağıtımı, 6–8 sürekli dağıtım, 9–13 DynamoDB deposu, 14–15 hesapta doğrulama.

- [x] 1. `Dockerfile` (FastAPI + arayüzler, kök olmayan kullanıcı, sağlık denetimi, varsayılan mock), `.dockerignore`, `.env.example` (açıklamalı, gizli değer yok; `.gitignore` → `!.env.example`)
  - _Gereksinimler: 1.1–1.6, 10.1–10.3_
- [x] 2. Image'ı yerelde derle ve sına: `docker build -t courier-memory .` + `docker run -p 8000:8000 courier-memory`; `/api/status` 200, `/story/` açılır, süreç `app` kullanıcısıyla
  - _Gereksinimler: 1.1–1.5_
- [x] 3. `deploy/web/ecs_deploy.py`: ECR deposu (tarama, son 10 image), `linux/amd64` derleme ve yükleme, `--skip-build` / `--image-tag`
  - _Gereksinimler: 2.1, 2.2, 3.1_
- [x] 4. Ağ ve servis: iki güvenlik grubu (internet → ALB:80, ALB → görev:8000), ALB (boşta 300 sn) + hedef grup (`/api/status`), log grubu (14 gün), görev tanımı (Fargate 1 vCPU / 2 GB), tek görevli servis (devre kesici + geri alma); tekrar çalıştırmak güvenli
  - _Gereksinimler: 3.2–3.8_
- [x] 5. IAM ve ortam: `courier-memory-web-exec`, `courier-memory-web-task` (yalnız izinli Sonnet/Haiku profilleri; `--extra-policy`), canlı mod ortamı ve `--env`; `deploy/web/README.md`
  - _Gereksinimler: 4.1–4.5_
- [x] 6. `deploy/ci/github_oidc_setup.py`: OIDC sağlayıcısı, yalnız `main` dalının üstlenebildiği `courier-memory-github-deploy` rolü, pipeline kaynaklarıyla sınırlı izinler
  - _Gereksinimler: 5.7–5.9_
- [x] 7. `.github/workflows/ci-cd.yml`: yalnız dağıtım (test yok, PR tetikleyicisi yok); `main`'de değişen dosyaya göre `deploy-web`, `deploy-agentcore` (`bootstrap.sh` + `verify.sh` + `agentcore deploy`), `deploy-quick`
  - _Gereksinimler: 5.1–5.6_
- [ ] 8. Pipeline sınaması: yalnız `ui/` değişince yalnız web; yalnız `deploy/quick/bridge_lambda.py` değişince yalnız köprü; el ile tetiklemede web + AgentCore
  - _Gereksinimler: 5.1–5.3_
- [ ] 9. Depo arayüzü: `CM_STORAGE` seçimi, dosya deposu (bugünkü dosyalar), açılışta açık hata; `MemoryBook`, `AgentFeed`, `LLM._log_usage` arayüze bağlanır; hızlı takım değişmeden yeşil
  - _Gereksinimler: 6.1–6.4_
- [ ] 10. DynamoDB deposu: hafıza kayıtları (tohum, sıfırlama, koşullu yazma), akış olayları (sıra sayacı, süzgeçler), kullanım kaydı (yalnız ekleme)
  - _Gereksinimler: 7.1–7.5, 8.1–8.3_
- [ ] 11. Anahtar şemasını kesinleştir; eşitlik ve eşzamanlılık testleri: iki depoda aynı senaryo aynı özeti verir, aynı kayda iki eşzamanlı güncelleme kaybolmaz (sahte DynamoDB istemcisi, AWS'siz)
  - _Gereksinimler: 7.4, 7.5, 9.3_
- [ ] 12. `deploy/dynamodb/create_table.py`: `CM_DYNAMODB_TABLE`, isteğe göre ödemeli, sunucu tarafı şifreleme; tablo varsa dokunmaz; yalnız bu tabloya izin veren politika
  - _Gereksinimler: 9.1–9.4_
- [ ] 13. Tablo deposuyla dağıtım: `ecs_deploy.py --env CM_STORAGE=dynamodb --env CM_DYNAMODB_TABLE=courier-memory --extra-policy <tablo politikası>`
  - _Gereksinimler: 4.4, 7.1_
- [ ] 14. Hesapta web doğrulaması: ALB adresinde `/api/status` 200, `/story/` açılır, canlı Orkestratör planı izle birlikte SSE ile kesilmeden gelir
  - _Gereksinimler: 11.1–11.3_
- [ ] 15. Hesapta kalıcılık doğrulaması: `CM_STORAGE=dynamodb` ile not bırak → yeniden dağıt → not kartta; `/api/feed` olayları korunur
  - _Gereksinimler: 7.1, 8.1, 11.4_
