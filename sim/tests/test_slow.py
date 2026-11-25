import time

import pytest

from cm_sim.config import load_config
from cm_sim.engine import Simulation
from cm_sim.run import DEMO_SCENARIOS


@pytest.mark.slow
def test_default_demo_under_60s():
    t = time.time()
    Simulation(load_config(scenarios=DEMO_SCENARIOS)).run()
    assert time.time() - t < 60


@pytest.mark.slow
def test_parse_accuracy_monotone():
    def far(acc, seed):
        res = Simulation(load_config(overrides=[f"seed={seed}", f"memory.parse_accuracy={acc}", "days.eval=8"])).run()
        d = res.arms["D"].daily
        return sum(x["ok"] for x in d) / sum(x["attempted"] for x in d)
    lo = sum(far(0.5, s) for s in (1, 2, 3)) / 3
    hi = sum(far(0.95, s) for s in (1, 2, 3)) / 3
    assert hi >= lo - 0.002
