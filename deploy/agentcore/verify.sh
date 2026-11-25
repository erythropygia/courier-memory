#!/usr/bin/env bash
# Courier Memory · AgentCore kontrolleri.
#
#   deploy/agentcore/verify.sh [ProjeAdı]              yerel ön kontrol (dağıtımdan önce; AWS gerekmez)
#   deploy/agentcore/verify.sh [ProjeAdı] --deployed   + dağıtımın üç kontrolü: Deploy, Tool, Observability
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS="${CM_WORKSPACE:-$(dirname "$REPO")}"
NAME="${1:-CourierMemory}"
MODE="${2:-}"
PROJ="$WS/$NAME"
APP="$PROJ/app/agent"
fail=0
ok()  { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; fail=1; }
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

echo "Yerel ön kontrol: $PROJ"
check "agentcore create iskelesi (agentcore/agentcore.json, agentcore/cdk)" '[ -f "$PROJ/agentcore/agentcore.json" ] && [ -d "$PROJ/agentcore/cdk" ]'
check "giriş noktası app/agent/main.py" '[ -f "$APP/main.py" ]'
check "bedrock_agentcore.runtime içe aktarımı (kökten değil)" 'grep -q "from bedrock_agentcore.runtime import BedrockAgentCoreApp" "$APP/main.py" && ! grep -q "^from bedrock_agentcore import" "$APP/main.py"'
check "tembel kurulum (_get_agent) ve @app.entrypoint asenkron işleyici" 'grep -q "def _get_agent" "$APP/main.py" && grep -q "@app.entrypoint" "$APP/main.py" && grep -q "async def invoke" "$APP/main.py"'
check "app.run() yalnız __main__ altında" 'grep -q "if __name__ == \"__main__\":" "$APP/main.py"'
check "gövdeden prompt ve actorId okunuyor" 'grep -q "actorId" "$APP/cm/payload.py"'
check "en az bir Strands @tool (cm/tools.py)" '[ "$(grep -c "^@tool" "$APP/cm/tools.py")" -ge 1 ]'
check "kimlik sınırı kancası (BeforeToolCallEvent)" 'grep -q "BeforeToolCallEvent" "$APP/cm/scope.py"'
check "çalışma kodu ve veri kopyalanmış (cm/backend.py, cm/core.py, data/demo_run)" '[ -f "$APP/cm/backend.py" ] && [ -f "$APP/cm/core.py" ] && [ -f "$APP/data/demo_run/meta.json" ]'
if [ -d "$APP/agents" ] && [ -d "$APP/cm_sim" ]; then echo "  · araç takımı: tam (alan kodu kopyalanmış; 9 araç)"; else echo "  · araç takımı: çekirdek (alan kodu yok; 6 araç, müdür araçları kapalı)"; fi
python3 - "$PROJ/agentcore/agentcore.json" "$APP" <<'PY' || fail=1
import json, pathlib, re, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8")); app = pathlib.Path(sys.argv[2]); bad = 0
def line(ok, text):
    global bad
    print(("  ✓ " if ok else "  ✗ ") + text); bad |= (not ok)
rts = cfg.get("runtimes") or []
line(bool(rts), "agentcore.json: runtime tanımlı (" + ", ".join(r.get("name", "?") for r in rts) + ")")
for r in rts:
    env = {e.get("name"): e.get("value") for e in r.get("envVars") or []}
    line(env.get("UNIFIED_TRACES_DESTINATION_ENABLED") == "true", f"gözlemlenebilirlik: {r.get('name')}.envVars UNIFIED_TRACES_DESTINATION_ENABLED=true")
mem = [m.get("name") for m in cfg.get("memories") or []]
line(bool(mem), "AgentCore Memory tanımlı (" + (", ".join(mem) or "yok") + ")")
ids = set()
for p in list(app.glob("model/*.py")) + [app / "cm" / "model.py"]:
    if p.exists():
        ids |= set(re.findall(r"[\"']((?:[a-z]+\.)?anthropic\.[a-z0-9.\-:]+)[\"']", p.read_text(encoding="utf-8")))
line(bool(ids) and all(i.split(".")[0] in ("global", "us", "eu", "apac", "au", "jp") for i in ids), "model kimliği çıkarım profili biçiminde: " + (", ".join(sorted(ids)) or "bulunamadı"))
deps = (app / "pyproject.toml").read_text(encoding="utf-8") if (app / "pyproject.toml").exists() else ""
m = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)^\]", deps)  # closing "]" on its own line, not one inside pkg[extra]
body = m.group(1).lower() if m else ""
if (app / "agents").is_dir():
    line(all(d in body for d in ("numpy", "scipy", "pydantic", "pyyaml")), "alan kodunun bağımlılıkları pyproject.toml'da (numpy, scipy, pydantic, pyyaml)")
line("pytest" not in body, "pytest [project].dependencies içinde değil (ARM64 derlemesi için)")
sys.exit(bad)
PY

if [ "$MODE" = "--deployed" ]; then
  cd "$PROJ" || exit 1
  RT="$(python3 -c "import json;print(json.load(open('agentcore/agentcore.json'))['runtimes'][0]['name'])")"
  echo; echo "Kontrol 1 · Deploy: agentcore status"
  STATUS="$(agentcore status --json 2>/dev/null)"
  ARN="$(printf '%s' "$STATUS" | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((r.get('arn') or '' for r in d.get('resources',[]) if r.get('resourceType')=='runtime'),''))" 2>/dev/null)"
  if [ -n "$ARN" ]; then ok "runtime dağıtılmış: $ARN"; else bad "runtime ARN bulunamadı (agentcore status çıktısına bakın; önce agentcore deploy)"; fi

  echo "Kontrol 2 · Tool: agentcore invoke (ajan bir aracını çağırmalı)"
  OUT="$(agentcore invoke --runtime "$RT" --payload '{"prompt":"Kullanım alanını bir cümleyle anlat, sonra araçlarından birini çağır ve ne döndürdüğünü göster."}' 2>&1)"
  TOOLS="$(printf '%s\n' "$OUT" | sed -n 's/^data: //p' | python3 -c "
import json,sys
names=[]
for l in sys.stdin:
    try: e=json.loads(l)
    except Exception: continue
    t=(((e.get('event') or {}).get('contentBlockStart') or {}).get('start') or {}).get('toolUse')
    if t: names.append(t.get('name'))
    if e.get('error'): print('ERROR:', e['error'], file=sys.stderr)
print(','.join(names))")"
  if [ -n "$TOOLS" ]; then ok "araç çağrıldı: $TOOLS"; else bad "akışta araç çağrısı yok"; printf '%s\n' "$OUT" | tail -5; fi

  echo "Kontrol 3 · Observability: log grubu ve izler"
  AGENT_ID="${ARN##*/}"
  # MSYS_NO_PATHCONV: Git Bash on Windows would otherwise rewrite "/aws/..." into a Windows path.
  if MSYS_NO_PATHCONV=1 aws logs describe-log-groups --log-group-name-prefix /aws/bedrock-agentcore/runtimes/ --query "logGroups[].logGroupName" --output text 2>/dev/null | tr '\t' '\n' | grep -q "/${AGENT_ID}-DEFAULT$"; then
    ok "log grubu var: /aws/bedrock-agentcore/runtimes/${AGENT_ID}-DEFAULT"
  else bad "log grubu yok: /aws/bedrock-agentcore/runtimes/${AGENT_ID}-DEFAULT"; fi
  echo "  izler (30–90 sn gecikebilir):"; agentcore traces runtime list --since 15m 2>&1 | head -8 | sed 's/^/    /'
fi

echo; [ "$fail" = 0 ] && echo "SONUÇ: tüm kontroller geçti." || echo "SONUÇ: eksik var (✗ satırları)."
exit "$fail"
