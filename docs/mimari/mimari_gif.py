"""Animated architecture chart: from the ROUTING MACHINE through every state of the agent chain.

Message of the chart: the chain runs on its own; courier knowledge is an optional booster that only enters through the
Memory Agent's validation gate. Wrong or missing courier input cannot break the plan.

Usage:  python docs/mimari/mimari_gif.py   (needs Pillow; macOS Arial fonts)
Output: docs/mimari/mimari-akis.gif
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("mimari-akis.gif")
K = 2                                   # supersampling factor
W, H = 1280, 770
FPS_MS = 90
SCENE_FRAMES = 48
OUT_W = 1024                            # output width; keeps the file small enough for slides and chat apps

FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / ("Arial Bold.ttf" if bold else "Arial.ttf")), size * K)


F_TITLE, F_NODE, F_SUB, F_SMALL, F_CAP_T, F_CAP = font(22, True), font(15, True), font(12), font(11, True), font(17, True), font(14)

BG = (13, 20, 36)
PANEL = (22, 32, 54)
TEXT = (226, 232, 240)
MUTED = (100, 116, 139)
DIM = (45, 58, 82)
BLUE = (59, 130, 246)
AMBER = (245, 158, 11)
GREEN = (34, 197, 94)
RED = (239, 68, 68)

NW, NH = 200, 80
NODES = {
    "rm": (40, 90, "ROUTING MACHINE", "Dinamik plan: kümeleme + rota"),
    "ork": (290, 90, "Orkestratör Ajanı", "Hacim, kapasite, komşu kurye"),
    "ata": (540, 90, "Atama Ajanı", "Çekirdek bölgeli plan"),
    "rota": (790, 90, "Hafızalı Rota", "Sert kısıt: rota uzamaz"),
    "onay": (1040, 90, "Acil Durum Kapısı", "Müdür yalnız acil durumda"),
    "brif": (1040, 240, "Brifing Ajanı", "Sabah brifingi, kapı ipucu"),
    "saha": (1040, 390, "Sahada Teslim", "Kurye kapıda"),
    "tes": (1040, 540, "Teslim Olayları", "Sistem kaydı: saat, sonuç"),
    "deg": (40, 240, "Değerlendirme Ajanı", "Her sabah öz-iyileştirme"),
    "haf": (540, 240, "Şube Hafızası", "Adres bazında, kaynak sayılı"),
    "kar": (790, 240, "Teyit Bekleyen", "Rotaya girmez, yalnız ipucu"),
    "has": (290, 390, "Hasat Ajanı", "Hedefli soru, ≤ 3/kurye/gün"),
    "kapi": (790, 390, "Hafıza Ajanı", "Doğrulama kapısı"),
    "kur": (540, 540, "Kurye Bilgisi", "Not · sesli · hasat cevabı"),
}
EDGES = {
    "rm_ork": [(240, 130), (290, 130)],
    "ork_ata": [(490, 130), (540, 130)],
    "ata_rota": [(740, 130), (790, 130)],
    "rota_onay": [(990, 130), (1040, 130)],
    "onay_brif": [(1140, 170), (1140, 240)],
    "brif_saha": [(1140, 320), (1140, 390)],
    "saha_tes": [(1140, 470), (1140, 540)],
    "tes_deg": [(1140, 620), (1140, 642), (18, 642), (18, 280), (40, 280)],
    "deg_rm": [(140, 240), (140, 170)],
    "deg_haf": [(240, 280), (540, 280)],
    "deg_has": [(140, 320), (140, 430), (290, 430)],
    "ata_has": [(560, 170), (560, 196), (515, 196), (515, 410), (490, 410)],
    "has_kur": [(390, 470), (390, 580), (540, 580)],
    "saha_kur": [(1040, 452), (1008, 452), (1008, 505), (700, 505), (700, 540)],
    "kur_kapi": [(740, 580), (850, 580), (850, 470)],
    "tes_kapi": [(1040, 595), (930, 595), (930, 470)],
    "kapi_haf": [(790, 430), (640, 430), (640, 320)],
    "kapi_kar": [(890, 390), (890, 320)],
    "haf_rota": [(690, 240), (690, 206), (840, 206), (840, 170)],
    "haf_brif": [(720, 240), (720, 222), (1016, 222), (1016, 262), (1040, 262)],
    "kar_brif": [(990, 300), (1040, 300)],
}
COURIER_EDGES = {"has_kur", "saha_kur", "kur_kapi", "ata_has", "deg_has"}   # drawn dashed: optional contribution
MAIN = ["rm_ork", "ork_ata", "ata_rota", "rota_onay", "onay_brif", "brif_saha", "saha_tes", "tes_deg", "deg_rm"]
MAIN_NODES = ["rm", "ork", "ata", "rota", "onay", "brif", "saha", "tes", "deg"]

# scene: (title, caption lines, badge, {edge: (color, start 0..1, label)}, {node: (color, tag)}, crossed nodes)
SCENES = [
    ("1 · Temel zincir: kuryeye bağlı değil",
     ["ROUTING MACHINE her sabah günün gönderilerini kümeler ve rotalar; ajanlar bunun üstünde çalışır:",
      "kapasite, çekirdek bölgeli atama, rota, brifing, teslim ve ertesi sabah öz-değerlendirme. Zincir temassızdır:",
      "acil durum yoksa plan müdüre gitmeden kesinleşir. Kurye bilgi vermese de plan uçtan uca çıkar; LLM düşerse kurallı yedek sürer."],
     ("Kurye bilgisi: yok  →  plan yine çıkar", BLUE),
     {e: (BLUE, i / len(MAIN) * 0.8, None) for i, e in enumerate(MAIN)} | {"deg_rm": (BLUE, 0.75, "ertesi sabah")},
     {n: (BLUE, None) for n in MAIN_NODES} | {"onay": (BLUE, "temassız")}, set()),
    ("2 · Kurye katkı verir: bilgi kapıdan geçerek zinciri güçlendirir",
     ["Hasat Ajanı yalnız boşluğa hedefli soru sorar; kurye notu ya da cevabı doğrudan rotaya gitmez.",
      "Hafıza Ajanı kişisel veriyi ve kapı şifresini ayıklar, türü ve süreyi çıkarır, sistem kaydıyla karşılaştırır.",
      "Kapıdan geçen bilgi rotaya kısıt, brifinge ipucu olur: rota uzamaz, yalnız iyileşir."],
     ("+ Katkı: kapıda geçen süre ↓  ilk denemede teslim ↑", GREEN),
     {"ata_has": (AMBER, 0.0, "boşluk"), "has_kur": (AMBER, 0.12, "soru"), "saha_kur": (AMBER, 0.12, "kapıda not"),
      "kur_kapi": (AMBER, 0.3, "not / cevap"), "tes_kapi": (GREEN, 0.3, "çapraz kontrol"),
      "kapi_haf": (GREEN, 0.5, "doğrulandı"), "haf_rota": (GREEN, 0.68, "kısıt"), "haf_brif": (GREEN, 0.68, "ipucu"),
      "rota_onay": (BLUE, 0.8, None), "onay_brif": (BLUE, 0.85, None)},
     {"has": (AMBER, None), "kur": (AMBER, None), "kapi": (GREEN, "geçti"), "haf": (GREEN, "+1 kayıt"),
      "rota": (GREEN, "iyileşti"), "brif": (GREEN, None), "saha": (BLUE, None), "tes": (BLUE, None)}, set()),
    ("3 · Kurye yanlış bilgi verirse",
     ["Tek kaynaklı bilgi rotayı değiştirmez: \"teyit bekleyen\" olur, brifingde yalnız \"kapıda teyit edin\" denir.",
      "Erteleme gibi rotayı değiştiren karar için en az iki bağımsız kaynak gerekir.",
      "İpucuna rağmen teslim başarısız olursa Değerlendirme Ajanı kaydı teyide alır; ≥ 2 çelişkide düşürür."],
     ("Yanlış bilgi zinciri bozamaz: rota değişmez", RED),
     {"kur_kapi": (RED, 0.0, "yanlış not"), "kapi_kar": (AMBER, 0.2, "tek kaynak"), "kar_brif": (AMBER, 0.38, "kapıda teyit et"),
      "brif_saha": (BLUE, 0.5, None), "saha_tes": (BLUE, 0.58, None), "tes_kapi": (RED, 0.66, "kayıt çelişiyor"),
      "tes_deg": (BLUE, 0.66, None), "deg_haf": (RED, 0.82, "teyide al / düşür")},
     {"kur": (RED, None), "kapi": (AMBER, "tek kaynak"), "kar": (AMBER, None), "rota": (BLUE, "değişmedi"),
      "deg": (RED, None), "haf": (RED, "düşürüldü"), "brif": (AMBER, None), "tes": (BLUE, None)}, set()),
    ("4 · Kurye bilgi vermeyi reddederse",
     ["Cevap gelmezse hiçbir şey beklemez: plan, rota ve brifing temel zincirle aynı şekilde çıkar.",
      "Sistem kendi teslim kayıtlarından öğrenmeye devam eder (adres × saat örüntüsü, tekrarlayan başarısızlık).",
      "Kayıttan çıkan hipotez teyitsiz hafızaya yazılmaz. Soru sınırı kurye başına günde 3: baskı yok, puanlama yok."],
     ("Cevap yok  →  rota temel plandan kötü olamaz", BLUE),
     {e: (BLUE, i / len(MAIN) * 0.7, None) for i, e in enumerate(MAIN)}
     | {"has_kur": (MUTED, 0.0, "cevap yok"), "tes_deg": (BLUE, 0.55, "kendi kayıtları")},
     {n: (BLUE, None) for n in MAIN_NODES} | {"kur": (RED, "cevap yok"), "deg": (BLUE, "kayıttan öğrenir")}, {"kur"}),
    ("5 · Bilgi bayatlarsa",
     ["Geçici bilgi (yol çalışması, tadilat) süresi dolunca kendiliğinden unutulur.",
      "Kurye kapıda \"değişmiş\" derse kayıt düşer; \"hâlâ geçerli\" derse kaynak sayısı artar.",
      "Değerlendirme Ajanı'nın her düşürme ve teyit kararı izde görünür ve geri alınabilir."],
     ("Hafıza kendini temizler", GREEN),
     {"saha_kur": (AMBER, 0.0, "\"değişmiş\""), "kur_kapi": (AMBER, 0.2, None), "kapi_haf": (RED, 0.4, "düşür"),
      "haf_rota": (GREEN, 0.62, "güncel kısıt"), "haf_brif": (GREEN, 0.62, None)},
     {"saha": (AMBER, None), "kur": (AMBER, None), "kapi": (GREEN, None), "haf": (GREEN, "süre doldu → unut"),
      "rota": (GREEN, None), "brif": (GREEN, None)}, set()),
    ("6 · Çok acil durum: müdür yalnız burada devreye girer",
     ["Acil Durum Kapısı kodla çalışır, LLM'e bırakılmaz. Plan müdüre yalnız şu durumlarda gider: kapasite açığı kapanmıyor,",
      "bir kuryede vardiya bandı 4 saatten fazla ya da şubede toplam 1500 dk aşılıyor, ajan planı çıkaramadı ya da plan kötüleşti.",
      "Simülasyonda 20 günün 2'si. Müdür, sistemin göremediği bir acil durumu (kaza, hava) kendisi de bildirebilir."],
     ("Müdür: yalnız acil durumda · 20 günün 2'si", RED),
     {"rm_ork": (BLUE, 0.0, None), "ork_ata": (BLUE, 0.1, None), "ata_rota": (BLUE, 0.2, None),
      "rota_onay": (RED, 0.32, "eşik aşıldı"), "onay_brif": (MUTED, 0.6, "müdür onayına kadar bekler")},
     {"rm": (BLUE, None), "ork": (BLUE, None), "ata": (BLUE, None), "rota": (RED, "+343 dk fazla mesai"),
      "onay": (RED, "müdüre eskale")}, set()),
    ("Özet · kurye bağımlılık değil, güçlendirici",
     ["Zincirin çalışması kuryeye bağlı değil; kalitesi kuryenin katkısıyla artar.",
      "Kurye bilgisi tek kapıdan girer, kaynak sayısıyla tartılır, sistem kaydıyla sınanır ve süresi dolunca unutulur.",
      "Zincir temassız çalışır; müdür yalnız çok acil durumda devreye girer. Hafıza büyüdükçe atama serbestleşir."],
     ("Ana zincir + doğrulanmış katkı", GREEN),
     {e: (BLUE, 0.0, None) for e in MAIN}
     | {"ata_has": (AMBER, 0.0, None), "has_kur": (AMBER, 0.0, None), "saha_kur": (AMBER, 0.0, None),
        "kur_kapi": (AMBER, 0.0, None), "tes_kapi": (GREEN, 0.0, None), "kapi_haf": (GREEN, 0.0, None),
        "kapi_kar": (AMBER, 0.0, None), "kar_brif": (AMBER, 0.0, None), "haf_rota": (GREEN, 0.0, None),
        "haf_brif": (GREEN, 0.0, None), "deg_haf": (GREEN, 0.0, None), "deg_has": (BLUE, 0.0, None)},
     {n: (BLUE, None) for n in MAIN_NODES} | {"onay": (BLUE, "temassız"), "kur": (AMBER, None), "has": (AMBER, None), "kapi": (GREEN, None),
                                             "haf": (GREEN, None), "kar": (AMBER, None)}, set()),
]


def s(v):
    return v * K


def pts(p):
    return [(s(x), s(y)) for x, y in p]


def mix(c, t, base=BG):
    return tuple(int(base[i] + (c[i] - base[i]) * t) for i in range(3))


def seg_len(p):
    return [math.dist(p[i], p[i + 1]) for i in range(len(p) - 1)]


def point_at(p, d):
    for i, L in enumerate(seg_len(p)):
        if d <= L:
            t = d / L if L else 0
            return (p[i][0] + (p[i + 1][0] - p[i][0]) * t, p[i][1] + (p[i + 1][1] - p[i][1]) * t)
        d -= L
    return p[-1]


def draw_poly(d, p, color, width, dashed=False):
    p = pts(p)
    if not dashed:
        d.line(p, fill=color, width=s(width), joint="curve")
    else:
        total, pos = sum(seg_len(p)), 0.0
        while pos < total:
            d.line([point_at(p, pos), point_at(p, min(pos + s(7), total))], fill=color, width=s(width))
            pos += s(12)
    (x1, y1), (x2, y2) = p[-2], p[-1]
    a = math.atan2(y2 - y1, x2 - x1)
    L = s(9)
    d.polygon([(x2, y2), (x2 - L * math.cos(a - 0.45), y2 - L * math.sin(a - 0.45)),
               (x2 - L * math.cos(a + 0.45), y2 - L * math.sin(a + 0.45))], fill=color)


LABEL_AT = {"tes_deg": (300, 630)}


def label_pos(p):
    """Midpoint of the longest segment, nudged off the line (or a fixed spot from LABEL_AT)."""
    for name, q in EDGES.items():
        if q is p and name in LABEL_AT:
            return LABEL_AT[name]
    lens = seg_len(p)
    i = max(range(len(lens)), key=lambda j: lens[j])
    (x1, y1), (x2, y2) = p[i], p[i + 1]
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return (mx + 8, my) if x1 == x2 else (mx, my - 12)


def text_c(d, xy, txt, f, fill):
    d.text((s(xy[0]), s(xy[1])), txt, font=f, fill=fill, anchor="mm")


def pill(d, cx, cy, txt, color, f=F_SMALL):
    w = d.textlength(txt, font=f) / K + 14
    d.rounded_rectangle([s(cx - w / 2), s(cy - 10), s(cx + w / 2), s(cy + 10)], radius=s(10), fill=color)
    text_c(d, (cx, cy), txt, f, BG)


def frame(scene, f):
    title, caption, badge, edges, nodes, crossed = scene
    t = f / SCENE_FRAMES
    img = Image.new("RGB", (s(W), s(H)), BG)
    d = ImageDraw.Draw(img)

    d.text((s(40), s(36)), "Courier Memory · mimari ve durum akışı", font=F_TITLE, fill=TEXT, anchor="lm")
    lx = 700
    for txt, col, dash in (("ana zincir", BLUE, False), ("kurye katkısı (opsiyonel)", AMBER, True),
                           ("doğrulanmış bilgi", GREEN, False), ("reddedilen / teyit", RED, False)):
        draw_poly(d, [(lx, 36), (lx + 26, 36)], col, 3, dash)
        d.text((s(lx + 34), s(36)), txt, font=F_SUB, fill=TEXT, anchor="lm")
        lx += 40 + d.textlength(txt, font=F_SUB) / K

    # edges: base layer
    for name, p in EDGES.items():
        active = name in edges and t >= edges[name][1]
        col = edges[name][0] if active else DIM
        draw_poly(d, p, col if active else DIM, 3 if active else 2, dashed=name in COURIER_EDGES)
    # pulses
    for name, (col, start, lab) in edges.items():
        if t < start or col == MUTED:
            continue
        p = pts(EDGES[name])
        total = sum(seg_len(p))
        phase = ((f - start * SCENE_FRAMES) * s(5)) % s(46)
        pos = phase
        while pos < total:
            x, y = point_at(p, pos)
            r = s(4)
            d.ellipse([x - r - s(3), y - r - s(3), x + r + s(3), y + r + s(3)], fill=mix(col, 0.35))
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
            pos += s(46)
    # nodes
    for key, (x, y, name, sub) in NODES.items():
        lit = key in nodes and key not in crossed
        col, tag = nodes.get(key, (DIM, None))
        border = col if lit else DIM
        fill = mix(col, 0.16, PANEL) if lit else PANEL
        if lit:
            glow = 0.5 + 0.5 * math.sin(f / 5)
            d.rounded_rectangle([s(x - 4), s(y - 4), s(x + NW + 4), s(y + NH + 4)], radius=s(16),
                                outline=mix(col, 0.25 + 0.25 * glow), width=s(3))
        d.rounded_rectangle([s(x), s(y), s(x + NW), s(y + NH)], radius=s(12), fill=fill, outline=border, width=s(2))
        if key in crossed:
            for i in range(0, NW, 14):
                d.line([s(x + i), s(y), s(x + min(i + 7, NW)), s(y)], fill=RED, width=s(3))
                d.line([s(x + i), s(y + NH), s(x + min(i + 7, NW)), s(y + NH)], fill=RED, width=s(3))
        text_c(d, (x + NW / 2, y + 30), name, F_NODE, TEXT if lit else MUTED)
        text_c(d, (x + NW / 2, y + 52), sub, F_SUB, (180, 192, 210) if lit else MUTED)
        if key == "rm":
            d.rounded_rectangle([s(x), s(y), s(x + 8), s(y + NH)], radius=s(4), fill=BLUE)
        if tag:
            pill(d, x + NW - 10 - d.textlength(tag, font=F_SMALL) / K / 2 - 7 + 10, y - 1, tag, RED if key in crossed else col)
    # edge labels on top
    for name, (col, start, lab) in edges.items():
        if lab and t >= start:
            lx_, ly_ = label_pos(EDGES[name])
            pill(d, lx_, ly_, lab, col if col != MUTED else (148, 163, 184))

    # caption panel
    d.rounded_rectangle([s(20), s(660), s(W - 20), s(H - 12)], radius=s(12), fill=PANEL)
    d.text((s(40), s(684)), title, font=F_CAP_T, fill=TEXT, anchor="lm")
    btxt, bcol = badge
    bw = d.textlength(btxt, font=F_SMALL) / K + 24
    d.rounded_rectangle([s(W - 40 - bw), s(672), s(W - 40), s(696)], radius=s(12), fill=bcol)
    d.text((s(W - 40 - bw / 2), s(684)), btxt, font=F_SMALL, fill=BG, anchor="mm")
    for i, line in enumerate(caption):
        d.text((s(40), s(710 + i * 19)), line, font=F_CAP, fill=(203, 213, 225), anchor="lm")
    # progress dots
    for i in range(len(SCENES)):
        cx = W / 2 - (len(SCENES) - 1) * 9 + i * 18
        on = SCENES[i] is scene
        r = 4 if on else 3
        d.ellipse([s(cx - r), s(H - 4 - r) - s(0), s(cx + r), s(H - 4 + r)], fill=TEXT if on else DIM)

    return img.resize((W, H), Image.LANCZOS)


def main():
    out_size = (OUT_W, round(H * OUT_W / W))
    frames = [frame(sc, f).resize(out_size, Image.LANCZOS) for sc in SCENES for f in range(SCENE_FRAMES)]
    picks = [frames[i * SCENE_FRAMES + SCENE_FRAMES - 1] for i in range(len(SCENES))]
    mosaic = Image.new("RGB", (out_size[0], out_size[1] * len(picks)))
    for i, fr in enumerate(picks):
        mosaic.paste(fr, (0, out_size[1] * i))
    pal = mosaic.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    # first frame = the summary, so viewers that show only one frame still show the whole chart
    seq = [picks[-1]] + frames
    q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in seq]
    durations = [1500]
    for _ in SCENES:
        durations += [FPS_MS] * (SCENE_FRAMES - 1) + [2200]       # hold the last frame of each scene
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(OUT, f"{OUT.stat().st_size / 1e6:.1f} MB", len(q), "frames")

if __name__ == "__main__":
    main()
