import pytest

from cm_sim.config import load_config

SMALL = [
    "world.addresses=1500", "couriers.senior=8", "couriers.reserve=1", "demand.shipments_per_day=600",
    "days.warmup=6", "days.eval=4",
]


@pytest.fixture
def small_cfg():
    def make(extra=(), scenarios=()):
        return load_config(scenarios=list(scenarios), overrides=SMALL + list(extra))
    return make
