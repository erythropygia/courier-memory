#!/usr/bin/env bash
# Courier Memory → AgentCore projesi.
#
#   deploy/agentcore/bootstrap.sh [ProjeAdı]        (varsayılan: CourierMemory)
#
# Ne yapar (tekrar çalıştırmak güvenlidir):
#   1. Proje yoksa `agentcore create --name <Ad> --template agent-python-strands` ile iskeleyi kurar
#      (klasör yapısı elle kurulmaz).
#   2. Şablonun main.py dosyasını <Proje>/.cm/main.template.py olarak saklar, bizimkini koyar.
#   3. Çalışma kodunu app/agent/ içine kopyalar: cm/ (Strands araçları, kimlik kancası, istem, hafıza) ve data/
#      (demo çalıştırması + gerçek gün). Repoda alan kodu varsa agents/, cm_sim/, config/ da kopyalanır (tam araç
#      takımı, 9 araç); yoksa ajan çekirdek takımla (6 araç, yalnız veri dosyaları) çalışır.
#   4. app/agent/pyproject.toml → [project].dependencies içine yalnız çalışma zamanı paketlerini ekler.
#   5. agentcore/agentcore.json → çalışma ortamının envVars listesine UNIFIED_TRACES_DESTINATION_ENABLED=true yazar.
# Dağıtmaz: `agentcore deploy` kararı sizde (deploy/agentcore/README.md).
#
# Ortam: CM_WORKSPACE (varsayılan: reponun üst klasörü), CM_SKIP_CREATE=1 (iskele zaten var; test için).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/deploy/agentcore/runtime"
WS="${CM_WORKSPACE:-$(dirname "$REPO")}"
NAME="${1:-CourierMemory}"
PROJ="$WS/$NAME"
APP="$PROJ/app/agent"

die() { echo "HATA: $*" >&2; exit 1; }
[[ "$NAME" =~ ^[A-Za-z][A-Za-z0-9]*$ ]] || die "Proje adı harfle başlamalı, yalnız harf ve rakam içermeli: $NAME"
mkdir -p "$WS"

if [ ! -f "$PROJ/agentcore/agentcore.json" ]; then
  [ "${CM_SKIP_CREATE:-0}" != "1" ] || die "$PROJ/agentcore/agentcore.json yok ve CM_SKIP_CREATE=1."
  command -v agentcore >/dev/null || die "agentcore CLI yok: önce AgentCore CLI'yi kurun (agentcore --version)."
  echo "==> agentcore create --name $NAME --template agent-python-strands  ($WS)"
  (cd "$WS" && agentcore create --name "$NAME" --template agent-python-strands)
fi
[ -d "$APP" ] || die "$APP yok: iskele beklenen yapıda değil (app/agent). agentcore/agentcore.json içindeki codeLocation'a bakın."

echo "==> şablonun main.py yedeği ve bizim giriş noktamız"
mkdir -p "$PROJ/.cm"
[ -f "$PROJ/.cm/main.template.py" ] || { [ -f "$APP/main.py" ] && cp "$APP/main.py" "$PROJ/.cm/main.template.py"; }
cp "$SRC/main.py" "$APP/main.py"

copy_tree() {  # copy_tree <kaynak> <hedef>: hedefi temizleyip kopyalar, önbellek ve testleri almaz
  rm -rf "$2"; mkdir -p "$2"
  (cd "$1" && tar --exclude='__pycache__' --exclude='tests' --exclude='*.pyc' -cf - .) | (cd "$2" && tar -xf -)
}
echo "==> çalışma kodu → $APP"
copy_tree "$SRC/cm" "$APP/cm"
mkdir -p "$APP/data"
copy_tree "$REPO/data/demo_run" "$APP/data/demo_run"
[ -d "$REPO/data/real_day" ] && copy_tree "$REPO/data/real_day" "$APP/data/real_day"
[ -d "$REPO/data/map" ] && copy_tree "$REPO/data/map" "$APP/data/map"
# Alan kodu (tam araç takımı). Repoda yoksa ajan çekirdek takımla çalışır.
TOOLSET=core
if [ -f "$REPO/agents/__init__.py" ] && [ -f "$REPO/sim/cm_sim/routing_memory.py" ]; then
  copy_tree "$REPO/agents" "$APP/agents"
  copy_tree "$REPO/sim/cm_sim" "$APP/cm_sim"
  copy_tree "$REPO/sim/config" "$APP/config"
  TOOLSET=full
else
  rm -rf "$APP/agents" "$APP/cm_sim" "$APP/config"
  echo "  not: agents/ ya da sim/cm_sim/ repoda yok → çekirdek araç takımı (6 araç). Alan kodu yazılınca betiği yeniden çalıştırın."
fi

echo "==> pyproject.toml bağımlılıkları ve agentcore.json envVars"
python3 - "$APP/pyproject.toml" "$PROJ/agentcore/agentcore.json" "$TOOLSET" <<'PY'
import json, re, sys
pyproject, agentcore, toolset = sys.argv[1], sys.argv[2], sys.argv[3]
# Çekirdek takım yalnız standart kütüphane kullanır; alan kodu numpy, scipy, pydantic ve pyyaml ister.
NEED = {"numpy": "numpy>=2.0", "scipy": "scipy>=1.13", "pydantic": "pydantic>=2.6", "pyyaml": "pyyaml>=6.0"} if toolset == "full" else {}
s = open(pyproject, encoding="utf-8").read()
m = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", s)
if not m:
    sys.exit("pyproject.toml içinde [project].dependencies bulunamadı")
have = {re.split(r"[<>=!~\[ ]", d.strip().strip('"\','))[0].lower() for d in m.group(1).split("\n") if d.strip().strip(",").strip()}
add = [v for k, v in NEED.items() if k not in have]
if add:
    body = m.group(1).rstrip()
    if body and not body.rstrip().endswith(","):
        body += ","
    body += "".join(f'\n    "{d}",' for d in add) + "\n"
    s = s[:m.start(1)] + body + s[m.end(1):]
    open(pyproject, "w", encoding="utf-8").write(s)
print("  bağımlılık eklendi:", ", ".join(add) if add else "(hepsi vardı)")

cfg = json.load(open(agentcore, encoding="utf-8"))
runtimes = cfg.get("runtimes") or []
if not runtimes:
    sys.exit("agentcore.json içinde runtime yok")
KEY = "UNIFIED_TRACES_DESTINATION_ENABLED"
for r in runtimes:
    env = [e for e in (r.get("envVars") or []) if e.get("name") != KEY]
    env.append({"name": KEY, "value": "true"})
    r["envVars"] = env
json.dump(cfg, open(agentcore, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("  envVars:", KEY, "= true →", ", ".join(r.get("name", "?") for r in runtimes))
print("  hafıza:", ", ".join(m.get("name", "?") for m in cfg.get("memories") or []) or "(tanımlı değil: agentcore add memory --name agentMemory)")
PY

if command -v uv >/dev/null; then
  echo "==> uv sync ($APP)"
  (cd "$APP" && uv sync >/dev/null 2>&1) || echo "  uyarı: uv sync başarısız; 'cd $APP && uv sync' çıktısına bakın."
fi

cat <<MSG

Hazır: $PROJ   (araç takımı: $TOOLSET)
Sıradaki adımlar (proje klasöründen):
  cd $PROJ
  $REPO/deploy/agentcore/verify.sh $NAME                 # yerel ön kontrol
  agentcore dev --port 8081                              # 1. terminal (8080 IDE'nindir, kullanmayın)
  agentcore invoke --runtime agent --local --port 8081 --payload '{"prompt":"Bugünkü brifingim?","actorId":"O02"}'
  agentcore deploy                                       # ilk dağıtım 5–8 dk
  $REPO/deploy/agentcore/verify.sh $NAME --deployed      # dağıtımın üç kontrolü
Model kimliği: app/agent/model/load.py çıkarım profili biçiminde olmalı (global.anthropic...). Şablonun main.py
dosyası .cm/main.template.py olarak saklandı; şablon hafıza ya da model kablolamasını değiştirdiyse karşılaştırın.
MSG
