"""Bilgi türleri (park, bina erişimi…), şifre koruması, durak kartları ve yaklaşma tetiği."""
import pytest

from agents import Services
from agents.memory import classify
from agents.cards import DOOR_M, SPEAK_MAX, APPROACH_M, StopCards
from agents.memorybook import MemoryWriteError
from agents.orchestrator import DayTools
from agents.route import MemoryConstraints
from agents.rundata import INFO_KINDS

PARK_NOTE = "binanın önü dar, arabayı köşedeki eczanenin önüne park edip yürüyün. kapı şifresi 4512"
FLOOR = "asansör yok 5. kata merdivenle çıkılıyor"


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    s.book.reset(s.run.meta["critical"]["day"])
    return s


@pytest.fixture
def ctx(sv):
    day, cid = sv.run.meta["critical"]["day"], sv.run.meta["critical"]["courier"]
    sc = StopCards(sv.run, sv.book, day, cid)
    stop = next(d for d in sc.stops if not d["cards"])
    return day, cid, stop


def _order(sv, day, cid):
    r = sv.run.route_of(day, cid)
    return DayTools(sv.run, sv.book, day).compute_route({"cluster_id": int(r["route"]), "courier_id": cid})["comparison"]["memory"]["order"]


def test_simulator_notes_never_become_info_kinds(sv):
    """Kurallı yedek: simülatör notları yalnız rotayı etkileyen türleri anlatır; bilgi türü eklemek sınıflandırmalarını değiştirmez."""
    assert not [n["text"] for n in sv.run.notes() if classify(n["text"]) in INFO_KINDS]
    assert classify("Arabayı arka sokağa park edin") == "park"
    assert classify("sokağa girilmiyo kazı var, aşağıya park et") == "roadwork"
    assert classify("trafik berbattı bugün") is None


def test_park_note_saved_secret_removed_route_unchanged(sv, ctx):
    day, cid, stop = ctx
    before = _order(sv, day, cid)
    n = sv.memory.process(day, cid, PARK_NOTE, stop["lat"], stop["lng"])
    assert n["status"] == "saved" and n["type"] == "park" and n["address"]["id"] == stop["address"]
    assert n["personal_data_redacted"] is True and "4512" not in n["hint"] and "şifre" not in n["hint"].lower()
    assert "eczane" in n["hint"]
    assert _order(sv, day, cid) == before                                    # bilgi türü rotaya girmez
    assert not [c for c in MemoryConstraints(sv.book, sv.run).constraints(day, [stop["address"]])]
    k = sv.memory.process(day, cid, FLOOR, stop["lat"], stop["lng"])
    assert k["type"] == "building_access" and "5. kat" in k["hint"]


def test_memory_write_rejects_secret_and_empty_info(sv, ctx):
    day, _, stop = ctx
    with pytest.raises(MemoryWriteError, match="şifre"):
        sv.book.upsert(address=stop["address"], kind="park", text="Kapı kodu 1234, otoparka girin.", day=day, note_id=None)
    with pytest.raises(MemoryWriteError, match="metni gerekli"):
        sv.book.upsert(address=stop["address"], kind="park", text="", day=day, note_id=None)
    with pytest.raises(MemoryWriteError, match="Bilinmeyen"):
        sv.book.upsert(address=stop["address"], kind="parking_spot", text="x", day=day, note_id=None)


def test_card_list_structured_and_ordered(sv, ctx):
    day, cid, stop = ctx
    sv.memory.process(day, cid, PARK_NOTE, stop["lat"], stop["lng"])
    sv.memory.process(day, cid, FLOOR, stop["lat"], stop["lng"])
    L = StopCards(sv.run, sv.book, day, cid).items()
    assert L["stop"] > L["stops_with_cards"] > 0 and L["type_distribution"]["park"] == 1
    assert [d["order"] for d in L["stops"]] == sorted(d["order"] for d in L["stops"])
    d = next(x for x in L["stops"] if x["address"] == stop["address"])
    assert [k["type"] for k in d["cards"]] == ["park", "building_access"]            # önce yaklaşırken
    p = d["cards"][0]
    assert p["moment"] == "approaching" and p["info_kind"] and not p["affects_route"] and p["confidence"] == "single_source"
    assert d["cards"][1]["moment"] == "at_door"
    sv.memory.process(day, cid, PARK_NOTE, stop["lat"], stop["lng"])                      # ikinci kaynak teyit eder
    d = next(x for x in StopCards(sv.run, sv.book, day, cid).items()["stops"] if x["address"] == stop["address"])
    assert d["cards"][0]["source_count"] == 2 and d["cards"][0]["confidence"] == "confirmed"


def test_approach_moment_and_no_repeat(sv, ctx):
    day, cid, stop = ctx
    sv.memory.process(day, cid, PARK_NOTE, stop["lat"], stop["lng"])
    sv.memory.process(day, cid, FLOOR, stop["lat"], stop["lng"])
    sc = StopCards(sv.run, sv.book, day, cid)
    s = stop["order"]
    far = sc.approach(stop["lat"] + 0.006, stop["lng"], next_order=s)       # ~660 m
    assert far["moment"] is None and not far["cards"] and far["pending"] == 2 and far["stop"]["distance_m"] > APPROACH_M
    near_ = sc.approach(stop["lat"] + 0.002, stop["lng"], next_order=s)        # ~220 m
    assert near_["moment"] == "approaching" and [k["type"] for k in near_["cards"]] == ["park"] and "eczane" in near_["to_speak"]
    door = sc.approach(stop["lat"], stop["lng"], next_order=s, shown=[k["id"] for k in near_["cards"]])
    assert door["moment"] == "at_door" and door["stop"]["distance_m"] <= DOOR_M and [k["type"] for k in door["cards"]] == ["building_access"]
    include_all = sc.approach(stop["lat"], stop["lng"], next_order=s)               # doğrudan kapıya: yaklaşırken kartı da söylenir
    assert [k["type"] for k in include_all["cards"]] == ["park", "building_access"] and len(include_all["cards"]) <= SPEAK_MAX
    done = sc.approach(stop["lat"], stop["lng"], next_order=s, shown=[k["id"] for k in include_all["cards"]])
    assert not done["cards"] and done["to_speak"] is None
    unordered = sc.approach(stop["lat"], stop["lng"])
    assert unordered["stop"]["address"] == stop["address"]
    with pytest.raises(ValueError):
        sc.approach(stop["lat"], stop["lng"], next_order=10_000)
