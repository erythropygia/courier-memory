"""Demo senaryosunun ajan yanıtlarını kaydeder (CM_LLM_MODE=record) ya da oynatarak doğrular (replay).

python -m agents.record
Aynı istekler canlı demoda replay modunda ağsız yanıtlanır. Arayüzdeki hazır soru ve not çipleri burada kayıtlıdır.
Orkestratör: günün planı + öneriyle gelen ilk iki senaryo sorusu. Kayıt anahtarı isteğin tamamıdır: istem, araç şeması ya da
araç çıktısı (hafıza durumu dahil) değişirse yeniden kaydedin; kayıttan önce hafıza sıfırlanır.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from . import Services

EXAMPLE_NOTES = [
    "zil bozuk Ayşe hanım çok huysuz telefonla arayın",
    "arka taraftan gir ön kapı açılmıyo",
    "trafik berbattı bugün",
    "öğlen kapalı 12den sonra gelme",
]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        sv = Services.create(memory_file=Path(td) / "mem.json")
        m = sv.run.meta
        day, cur, name = m["critical"]["day"], m["critical"]["courier"], m["critical"]["courier_name"]
        print(f"Mod: {sv.llm.mode} · gün {day} · kurye {cur} ({name})")
        sv.book.reset(day)
        time_source(sv.run).reset()
        t = time.time()
        o = sv.orchestrator.plan(day)
        print(f"orkestrator/planla: degraded={o['degraded']} olay={len(o['trace'])} ({time.time() - t:.1f} sn)")
        for q in o["proposal"]["questions"][:2]:
            t = time.time()
            a = sv.orchestrator.ask(day, q, o["proposal"])
            print(f"orkestrator/sor '{q}': degraded={a['degraded']} ({time.time() - t:.1f} sn)")
        t = time.time()
        r = sv.assignment.propose(day)
        print(f"atama/oner: degraded={r['degraded']} ({time.time() - t:.1f} sn)")
        for q in (f"{name} gelmezse ne olur?", f"{name} yerine yedek kurye gönderirsem?"):
            t = time.time()
            a = sv.assignment.ask(day, q)
            print(f"atama/sor '{q}': degraded={a['degraded']} ({time.time() - t:.1f} sn)")
        t = time.time()
        b = sv.briefing.prepare(day, cur)
        print(f"brifing: degraded={b['degraded']} ({time.time() - t:.1f} sn)")
        t = time.time()
        hv = sv.harvest.plan(day)            # Faz 2: hasat soruları; ilk sorunun simüle cevabı Hafıza Ajanı'ndan geçer
        if hv["questions"]:
            sv.harvest.simulate_answer(hv["questions"][0]["id"])
        print(f"hasat: degraded={hv['degraded']} soru={len(hv['questions'])} ({time.time() - t:.1f} sn)")
        stop = b["route"]["stops"][5]
        for n in EXAMPLE_NOTES:
            t = time.time()
            h = sv.memory.process(day, cur, n, stop[1], stop[2], None, stop[4])
            print(f"not '{n[:30]}…': {h['status']} degraded={h['degraded']} ({time.time() - t:.1f} sn)")
    print(f"Kayıt sayısı: {sv.llm.cassette_count()} (cassettes/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
