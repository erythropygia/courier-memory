from cm_sim.engine import Simulation

OFF = [
    "couriers.skill_sigma=0", "couriers.speed_sigma=0", "outcome.eta_nav=0", "outcome.nav_min=0",
    "outcome.delta_wrong=0", "outcome.tau_wrong=0", "quirks.prevalence_scale=0", "quirks.temporary_rate=0",
    # Faz 2b: alıcı yokluğu varış saatine bağlı (rota etkisi, bilgi değil); rota farkı sonucu değiştirmesin diye kapalı.
    "presence.enabled=false",
]


def test_knowledge_off_arms_bcd_identical(small_cfg):
    """Bilgi etkileri kapalıyken B, C, D aynı sonucu vermeli: CRN + politika izolasyonu birlikte çalışıyor."""
    res = Simulation(small_cfg(OFF)).run()
    for i in range(len(res.eval_days)):
        rows = [res.arms[a].daily[i] for a in "BCD"]
        assert len({(r["ok"], r["fail"], r["deferred"]) for r in rows}) == 1, rows


def test_knowledge_on_ordering(small_cfg):
    res = Simulation(small_cfg()).run()
    far = {a: sum(d["ok"] for d in res.arms[a].daily) / sum(d["attempted"] for d in res.arms[a].daily) for a in "ABCD"}
    assert far["C"] > far["B"]
