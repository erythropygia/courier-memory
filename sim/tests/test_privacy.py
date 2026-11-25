import dataclasses

import numpy as np

from cm_sim.couriers import Courier
from cm_sim.engine import Simulation
from cm_sim.world import Quirk, World

HIDDEN = (Courier, Quirk, World)


def _walk(obj, seen, path="arg"):
    if id(obj) in seen or isinstance(obj, (str, int, float, bool, type(None), np.ndarray, np.generic)):
        return
    seen.add(id(obj))
    assert not isinstance(obj, HIDDEN), f"Gizli nesne politikaya sızdı: {path} ({type(obj).__name__})"
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            _walk(getattr(obj, f.name), seen, f"{path}.{f.name}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, seen, f"{path}[{k!r}]")
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            _walk(v, seen, f"{path}[{i}]")
    elif hasattr(obj, "__dict__") and type(obj).__module__.startswith("cm_sim"):
        for k, v in vars(obj).items():
            _walk(v, seen, f"{path}.{k}")


class Spy:
    def __init__(self, inner):
        self.inner, self.name, self.calls = inner, inner.name, 0

    def _check(self, ctx, *objs):
        self.calls += 1
        seen: set[int] = set()
        for i, o in enumerate(objs):
            _walk(o, seen, f"arg{i}")
        _walk(ctx.history._h, seen, "history")            # geçmiş kayıtları
        _walk(dict(ctx.history._f.state), seen, "familiarity")
        if ctx.memory is not None:
            _walk(ctx.memory.entries, seen, "memory")

    def assign(self, ctx, clusters, couriers):
        self._check(ctx, clusters, couriers)
        return self.inner.assign(ctx, clusters, couriers)

    def plan(self, ctx, stops, couriers, k, seed, extra_w=None):
        self._check(ctx, stops, couriers, extra_w)
        return self.inner.plan(ctx, stops, couriers, k, seed, extra_w=extra_w)


def test_policies_never_receive_hidden_objects(small_cfg):
    sim = Simulation(small_cfg())
    spies = {a: Spy(p) for a, p in sim.policies.items()}
    sim.policies = spies
    sim.run()
    # D kendi (hafıza-farkında) planını kurar: B, C ve D politikalarının hepsi çağrılmış olmalı.
    assert spies["B"].calls > 0 and spies["C"].calls > 0 and spies["D"].calls > 0
