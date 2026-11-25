# Courier Memory web uygulaması: FastAPI + arayüzler (/story, /flow, /ui) tek container'da.
#   docker build -t courier-memory .
#   docker run -p 8000:8000 -e CM_LLM_MODE=mock courier-memory
# Canlı Bedrock için: CM_LLM_MODE=live CM_BEDROCK_CLIENT=invoke CM_MODEL_ID=global.anthropic.claude-sonnet-5 AWS_REGION=us-east-1
# (kimlik standart AWS zincirinden gelir; ECS'te görev rolü). Ayrıntı: deploy/web/README.md
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/sim \
    CM_LLM_MODE=mock CM_MEMORY_FILE=/tmp/cm/live_memory.json

WORKDIR /app

# Bağımlılıklar ayrı katmanda: kod değişince yeniden kurulmaz.
RUN pip install --no-cache-dir "numpy>=2.0" "scipy>=1.13" "pydantic>=2.6" "pyyaml>=6.0" \
        "fastapi>=0.110" "uvicorn[standard]>=0.29" "anthropic[bedrock]>=2.0"

# Uygulama kaynak ağacından çalışır (api/main.py arayüzleri reponun kökünden okur).
COPY sim/cm_sim sim/cm_sim
COPY sim/config sim/config
COPY agents agents
COPY api api
COPY data data
COPY ui ui

RUN useradd --create-home --uid 10001 app && mkdir -p /tmp/cm && chown -R app /tmp/cm /app/data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=4)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
