import pytest
import yaml

from cm_sim.config import load_config
from cm_sim.calibration import TARGETS, measure


@pytest.mark.slow
def test_calibration_all_targets_within_tolerance():
    tg = yaml.safe_load(TARGETS.read_text(encoding="utf-8"))["targets"]
    m = measure(load_config())
    bad = {k: (t["target"], round(m[k], 4)) for k, t in tg.items() if abs(m[k] - t["target"]) > t["tolerance"] * abs(t["target"])}
    assert not bad, f"Kalibrasyon dışı: {bad}"
