#!/usr/bin/env bash
# Repo içindeki Kiro dosyalarını çalışma alanı köküne taşır.
#
# Kiro steering, spec, skill, hook ve MCP ayarını çalışma alanının kökündeki .kiro klasöründen okur. Etkinlikte çalışma
# alanı ~/environment'tır; repo onun altında bir klasördür. Bu betik repo/.kiro içeriğini ~/environment/.kiro altına kopyalar.
#
#   deploy/kiro_sync.sh            var olan dosyaya dokunmaz (atölyenin steering ve skill dosyaları korunur)
#   deploy/kiro_sync.sh --force    bizim dosyalarımızı günceller (atölyenin dosyaları yine korunur: adları farklıdır)
#
# Ortam: CM_WORKSPACE (varsayılan ~/environment).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${CM_WORKSPACE:-$HOME/environment}"
FORCE="${1:-}"
SRC="$REPO/.kiro"
DST="$WS/.kiro"
mkdir -p "$DST/steering" "$DST/specs" "$DST/skills" "$DST/hooks" "$DST/settings"

copied=0; kept=0
copy() {  # copy <kaynak dosya> <hedef dosya>
  mkdir -p "$(dirname "$2")"
  if [ -e "$2" ] && [ "$FORCE" != "--force" ]; then kept=$((kept + 1)); else cp "$1" "$2"; copied=$((copied + 1)); fi
}
while IFS= read -r f; do copy "$SRC/$f" "$DST/$f"; done < <(cd "$SRC" && find steering specs skills hooks -type f | sort)

# Çalışma alanına özgü steering: reponun yeri (spec ve steering içindeki yollar buna göredir)
cat > "$DST/steering/cm-workspace.md" <<MD
---
inclusion: always
---
# Courier Memory: çalışma alanı

- Repo: \`$REPO\` (steering ve spec dosyalarındaki \`agents/\`, \`api/\`, \`deploy/\`, \`docs/\` yolları bu klasöre göredir).
- AgentCore projesi: \`$WS/CourierMemory\` (\`deploy/agentcore/bootstrap.sh\` kurar). \`app/agent/\` altındaki \`cm/\`, \`agents/\`, \`cm_sim/\`, \`data/\` kopyadır; repoda düzenle.
- Komutlar: \`$REPO/deploy/agentcore/bootstrap.sh\`, \`$REPO/deploy/agentcore/verify.sh [--deployed]\`, \`$REPO/deploy/kiro_sync.sh --force\` (repodaki Kiro dosyaları değişince).
- Yerel API: \`cd $REPO && CM_LLM_MODE=mock uvicorn api.main:app --host 0.0.0.0 --port 8000\`; tarayıcıda \`\$IDE_URL/proxy/8000/flow/\`. 8080 ve 8081 kullanılmaz.
MD

# MCP: projenin sunucusunu çalışma alanı ayarına mutlak yolla ekler; var olan sunuculara dokunmaz
python3 - "$DST/settings/mcp.json" "$REPO" <<'PY'
import json, os, sys
path, repo = sys.argv[1], sys.argv[2]
cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
servers = cfg.setdefault("mcpServers", {})
servers["courier-memory"] = {
    "command": os.path.join(repo, ".venv", "bin", "python"),      # README'deki kurulumun ortamı (pip install -e ".[dev,agentcore]")
    "args": [os.path.join(repo, "deploy", "mcp", "cm_mcp_server.py")],
    "env": {"CM_LLM_MODE": "mock", "PYTHONUTF8": "1"},
    "disabled": False,
    "autoApprove": ["branch_memory_summary", "address_memory", "courier_stop_cards", "real_day_evidence", "demo_context"],
}
json.dump(cfg, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("  MCP sunucuları:", ", ".join(sorted(servers)))
PY

echo "Kiro dosyaları: $copied kopyalandı, $kept korundu → $DST"
echo "  steering: $(ls "$DST/steering" | tr '\n' ' ')"
echo "  specs:    $(ls "$DST/specs" | tr '\n' ' ')"
echo "  skills:   $(ls "$DST/skills" | tr '\n' ' ')"
echo "  hooks:    $(ls "$DST/hooks" | tr '\n' ' ')"
echo "Kiro'da yeni oturum açın (ya da sekmeyi yenileyin); skill'ler sohbetin / listesinde, hook'lar Hooks panelinde görünür."
