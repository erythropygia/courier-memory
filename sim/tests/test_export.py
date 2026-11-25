import json

from cm_sim.engine import Simulation
from cm_sim.export import STOP_FIELDS, export_run


def test_export_files_and_app_data_flag(tmp_path, small_cfg):
    out = export_run(Simulation(small_cfg()).run(), tmp_path)
    for name in ("meta.json", "summary.json", "daily.json", "blocks.json", "addresses.json", "couriers.json",
                 "notes.json", "notes_truth.json", "truth.json", "recovery.json", "learning_curve.json", "report.md"):
        assert (out / name).exists(), name
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    day = meta["eval_days"][0]
    for arm in "ABCD":
        snap = json.loads((out / "snapshots" / arm / f"{day}.json").read_text(encoding="utf-8"))
        assert snap["app_data"] is True and snap["stop_fields"] == STOP_FIELDS
    a = json.loads((out / "assign" / "D" / f"{day}.json").read_text(encoding="utf-8"))
    assert len(a["cost"]) == len(a["couriers"]) and len(a["cost"][0]) == len(a["clusters"])
    for p in out.rglob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8")).get("app_data") is True, p
    assert "skill" not in (out / "couriers.json").read_text(encoding="utf-8")
