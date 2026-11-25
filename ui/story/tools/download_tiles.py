"""Çevrimdışı harita: OpenFreeMap (OpenMapTiles şeması) vektör karolarını ve Noto Sans glyph'lerini ui/story/ altına indirir.

  python ui/story/tools/download_tiles.py
Ana kapsam (Beykoz + Boğaz) z8–14 (OpenFreeMap en çok z14 verir; üstü MapLibre'de büyütülür), bağlam z7–10 geniş alan.
Var olan dosya atlanır. ~23 MB. Atıf: OpenFreeMap © OpenMapTiles © OpenStreetMap katkıcıları.
"""
import concurrent.futures as cf
import json
import math
import os
import urllib.request
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "tile-prefetch/1.0"}
COVERAGE = [((28.98, 41.00, 29.40, 41.28), range(8, 15)), ((28.5, 40.7, 30.0, 41.7), range(7, 11))]
FONTS = ["Noto Sans Regular", "Noto Sans Bold", "Noto Sans Italic"]
INTERVAL = ["0-255", "256-511", "768-1023", "8192-8447"]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def xy(lon, lat, z):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def main():
    tiles = json.loads(get("https://tiles.openfreemap.org/planet"))["tiles"][0]
    jobs = set()
    for (w, s, e, n), zs in COVERAGE:
        for z in zs:
            (x0, y0), (x1, y1) = xy(w, n, z), xy(e, s, z)
            jobs |= {(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}

    def download(j):
        z, x, y = j
        p = UI / "tiles" / str(z) / str(x) / f"{y}.pbf"
        if p.exists():
            return 0
        p.parent.mkdir(parents=True, exist_ok=True)
        b = get(tiles.format(z=z, x=x, y=y))
        p.write_bytes(b)
        return len(b)

    with cf.ThreadPoolExecutor(6) as ex:
        print("tile", len(jobs), "yeni bayt", sum(ex.map(download, sorted(jobs))))
    for f in FONTS:
        for r in INTERVAL:
            p = UI / "fonts" / f / f"{r}.pbf"
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(get(f"https://tiles.openfreemap.org/fonts/{f.replace(' ', '%20')}/{r}.pbf"))
    print("glyph tamam")


if __name__ == "__main__":
    os.chdir(UI)
    main()
