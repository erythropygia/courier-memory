import numpy as np

from cm_sim.config import load_config
from cm_sim.demand import demand_for_day
from cm_sim.planning import plan_dynamic
from cm_sim.rng import rng
from cm_sim.world import build_world


def test_dynamic_clusters_cover_all_stops_and_are_balanced():
    cfg = load_config()
    w = build_world(cfg)
    day = cfg.days.warmup + 2
    counts = demand_for_day(cfg, w, day)
    stops = np.flatnonzero(counts)
    routes = plan_dynamic(cfg, w, stops, counts, 22, rng(cfg.seed, day, 99))
    allstops = np.concatenate([r.stops for r in routes])
    assert sorted(allstops.tolist()) == sorted(stops.tolist())
    assert len(routes) <= 22
    mins = np.array([r.planned_minutes for r in routes])
    assert mins.std() / mins.mean() < 0.15


def test_cluster_count_capped_by_available():
    cfg = load_config()
    w = build_world(cfg)
    counts = demand_for_day(cfg, w, 3)
    stops = np.flatnonzero(counts)
    routes = plan_dynamic(cfg, w, stops, counts, 5, rng(1, 2, 3))
    assert len(routes) <= 5
