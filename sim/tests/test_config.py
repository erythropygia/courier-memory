import pytest

from cm_sim.config import ConfigError, load_config


def test_default_loads():
    cfg = load_config()
    assert cfg.days.warmup > 0 and cfg.couriers.senior > 0


def test_override_and_error_path():
    cfg = load_config(overrides=["couriers.senior=12"])
    assert cfg.couriers.senior == 12
    with pytest.raises(ConfigError) as e:
        load_config(overrides=["couriers.senior=-1"])
    assert "couriers.senior" in str(e.value)
    with pytest.raises(ConfigError) as e:
        load_config(overrides=["couriers.offline=1"])
    assert "offline" in str(e.value)


def test_scenarios_merge_lists():
    cfg = load_config(scenarios=["leave_wave", "turnover", "borrowed_courier"])
    assert len(cfg.calendar.leaves) == 3 and len(cfg.calendar.hires) == 2 and len(cfg.calendar.borrowed) == 3
    assert len(cfg.demand.shocks) == 3
