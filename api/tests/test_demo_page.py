"""Demo izi sayfasının üreticisi (ui/demo/build.py): sekiz halka, dört bölüm, şifre sızmaz, hafıza değişmez."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_build():
    spec = importlib.util.spec_from_file_location("demo_build", ROOT / "ui" / "demo" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_run_has_eight_links_and_no_secret():
    memory = ROOT / "data" / "live_memory.json"
    before = memory.read_text(encoding="utf-8") if memory.exists() else None
    data = load_build().run()
    steps = data["steps"]
    assert len(steps) == 8
    assert [s["agent"] for s in steps][:2] == ["Orkestratör Ajanı", "Acil Durum Kapısı"]
    for s in steps:
        assert s["took"] and s["trace"] and s["gave"], s["agent"]
        assert s["source"] in ("rule", "llm")                            # temassız zincir: demo gününde insan adımı yok
    assert steps[1]["gave"]["head"].startswith("Plan kesinleşti")
    tools = [t for s in steps for t in s["trace"] if t.get("tool")]
    assert len(tools) >= 20 and all("params" in t and t["summary"] for t in tools)   # her çağrı: gerçek parametre + sonuç
    orch = steps[0]["trace"]
    assert any(t.get("tool") == "core_assignment" and t["params"].get("borrowed") for t in orch)
    assert steps[0]["requests"][0]["call"] == "POST /api/orchestrator/start"              # ajanın aldığı gerçek istek
    memory_step = next(s for s in steps if s["agent"] == "Hafıza Ajanı")
    assert "2580" not in json.dumps(memory_step["gave"], ensure_ascii=False)
    assert "2580" not in json.dumps(memory_step["trace"], ensure_ascii=False)
    if before is not None:
        assert json.loads(memory.read_text(encoding="utf-8")) == json.loads(before)
