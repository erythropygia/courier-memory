import json

import numpy as np

from cm_sim.engine import Simulation
from cm_sim.export import export_run
from cm_sim.rng import day_streams


def test_same_seed_same_summary(tmp_path, small_cfg):
    outs = []
    for i in range(2):
        res = Simulation(small_cfg()).run()
        outs.append(export_run(res, tmp_path / str(i), snapshots=False))
    a = (outs[0] / "summary.json").read_bytes()
    b = (outs[1] / "summary.json").read_bytes()
    assert a == b


def test_crn_streams_identical_per_day():
    counts = np.array([1, 0, 3, 2])
    s1, s2 = day_streams(7, 25, counts), day_streams(7, 25, counts)
    assert np.array_equal(s1.u_stop, s2.u_stop) and np.array_equal(s1.u_ship, s2.u_ship)
    s3 = day_streams(7, 26, counts)
    assert not np.array_equal(s1.u_stop, s3.u_stop)


def test_different_seed_differs(small_cfg):
    a = Simulation(small_cfg(["seed=1"])).run().arms["D"].daily
    b = Simulation(small_cfg(["seed=2"])).run().arms["D"].daily
    assert json.dumps(a) != json.dumps(b)
