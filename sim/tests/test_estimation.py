import numpy as np
import pytest

from cm_sim.config import load_config
from cm_sim.engine import Simulation
from cm_sim.estimation import report_recovery, solve_assignment
from cm_sim.history import HistoryReader


def test_solve_assignment_respects_exclude_and_fixed():
    cost = np.array([[1.0, 9.0], [9.0, 1.0], [2.0, 2.0]])
    m = solve_assignment(cost, ["a", "b", "c"], [10, 20])
    assert m == {10: "a", 20: "b"}
    m = solve_assignment(cost, ["a", "b", "c"], [10, 20], exclude={"a"})
    assert m == {10: "c", 20: "b"}
    m = solve_assignment(cost, ["a", "b", "c"], [10, 20], fixed={20: "a"})
    assert m[20] == "a" and m[10] in ("b", "c")
    with pytest.raises(ValueError):
        solve_assignment(cost, ["a", "b", "c"], [10, 20], exclude={"a", "b"})


@pytest.mark.slow
def test_estimator_beats_naive_on_average():
    est, naive = [], []
    for seed in (2, 3, 4):
        cfg = load_config(overrides=[f"seed={seed}", "days.eval=6"])
        res = Simulation(cfg).run()
        truth = {c.id: c.skill for c in res.couriers}
        h = HistoryReader(res.arms["C"].history, res.arms["C"].fam, 0.2, res.world.block_kind)
        r = report_recovery(h, truth, cfg.assignment)
        est.append(r["spearman_estimate"])
        naive.append(r["spearman_naive"])
    assert np.mean(est) > 0.4
    assert np.mean(est) >= np.mean(naive)
