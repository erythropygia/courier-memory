"""Animated AWS infrastructure chart, kept simple: every service with what it does and WHY we use it.

The chain is triggered by the ROUTING MACHINE. Companion to mimari_gif.py (same visual language).

Usage:  python docs/mimari/aws_gif.py   (needs Pillow; macOS Arial fonts)
Output: docs/mimari/aws-altyapi.gif
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("aws-altyapi.gif")
K = 2                                   # supersampling factor
W, H = 1280, 770
FPS_MS = 90
SCENE_FRAMES = 48
OUT_W = 1024

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
_fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (round(size * K), bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(FONT_DIR / ("Arial Bold.ttf" if bold else "Arial.ttf")), key[0])
    return _fonts[key]


F_TITLE, F_SUB, F_SMALL, F_CAP_T, F_CAP, F_ZONE = font(21, True), font(12), font(11, True), font(17, True), font(14), font(11, True)

BG = (13, 20, 36)
PANEL = (22, 32, 54)
TEXT = (226, 232, 240)
MUTED = (100, 116, 139)
DIM = (45, 58, 82)
BLUE = (59, 130, 246)
AMBER = (245, 158, 11)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
PURPLE = (168, 85, 247)
TEAL = (45, 212, 191)
GREY = (148, 163, 184)
WHY = (253, 224, 138)

C1, C2, C3, C4 = 30, 345, 660, 975          # column x
NW, NH = 275, 84
RA, RB, RC, RD = 86, 206, 326, 500          # row y

# key: (x, y, name, what, why, category color)
NODES = {
    "rm": (C1, RA, "ROUTING MACHINE", "Her sabah kümeleme + rota", "Neden: zinciri tetikler; plan bunun üstüne kurulur", BLUE),
    "rt": (C2, RA, "Bedrock AgentCore Runtime", "5 ajan: yönetici, planlama, kurye, hafıza, analiz", "Neden: ajanlar sunucusuz ve kimlik sınırlı çalışır", BLUE),
    "llm": (C3, RA, "Amazon Bedrock · Claude", "Ajanların modeli: araç kullanarak karar", "Neden: karar modelde, her sayı deterministik araçta", BLUE),
    "cw": (C4, RA, "Amazon CloudWatch", "Loglar ve OpenTelemetry izleri", "Neden: her karar izlenir, hata anında görülür", RED),
    "quick": (C1, RB, "Amazon Quick", "MCP ile AgentCore Gateway'e bağlı", "Neden: ekip doğal dille sorar, panoda görür", TEAL),
    "mem": (C2, RB, "AgentCore Memory", "Oturum hafızası, kimlik başına ayrı alan", "Neden: ajan bağlamı unutmaz, veriler karışmaz", BLUE),
    "ddb": (C3, RB, "Amazon DynamoDB", "Kalıcı şube adres hafızası", "Neden: bilgi kişiden adrese taşınır, kalıcı kalır", GREEN),
    "iam": (C4, RB, "AWS IAM · en az yetki", "Rol politikaları: çağrı ve veri erişimi dar", "Neden: analiz salt okunur, yetkisiz erişim yok", RED),
    "kiro": (C1, RC, "Kiro + MCP sunucusu", "Spec → tasarım → görev; steering, hook", "Neden: önce spec; hafıza geliştirirken okunur", AMBER),
    "dep": (C2, RC, "agentcore deploy · AWS CDK", "5 runtime + hafıza + IAM'i kurar", "Neden: altyapı kodla, tek komutla tekrar kurulur", AMBER),
    "ath": (C4, RC, "Amazon S3 + Glue + Athena", "Geçmiş teslim verisi, 4 tablo", "Neden: Analiz Ajanı geçmişi sunucusuz sorgular", GREEN),
    "trn": (C2, RD, "Amazon Transcribe", "Kuryenin sesli notu → metin", "Neden: kurye direksiyonda yazmadan not bırakır", PURPLE),
    "pol": (C3, RD, "Amazon Polly", "Kapı kartı → doğal Türkçe ses", "Neden: kurye ekrana bakmadan duyar", PURPLE),
}

ZONES = [  # (x1, y1, x2, y2, label, color)
    (16, 470, 1262, 600, "Sesli döngü · Transcribe + DynamoDB + Polly", PURPLE),
]

EDGES = {
    "rm_rt": [(C1 + NW, 122), (C2, 122)],
    "rt_llm": [(C2 + NW, 110), (C3, 110)],
    "rt_cw": [(C2 + 160, RA), (C2 + 160, 72), (C4 + 137, 72), (C4 + 137, RA)],
    "rt_mem": [(C2 + 137, RA + NH), (C2 + 137, RB)],
    "rt_ddb": [(C2 + NW, 140), (640, 140), (640, 248), (C3, 248)],
    "rt_ath": [(C2 + NW, 160), (652, 160), (652, 312), (C4 + 137, 312), (C4 + 137, RC)],
    "quick_rt": [(C1 + NW, 248), (325, 248), (325, 150), (C2, 150)],
    "kiro_dep": [(C1 + NW, 368), (C2, 368)],
    "dep_rt": [(C2 + 137, RC), (C2 + 137, RB + NH)],
    "rm_ath": [(C1, 150), (18, 150), (18, 444), (C4 + 70, 444), (C4 + 70, RC + NH)],
    "voice_in": [(40, 542), (C2, 542)],
    "trn_ddb": [(C2 + NW - 20, RD), (C2 + NW - 20, 458), (705, 458), (705, RB + NH)],
    "ddb_pol": [(860, RB + NH), (860, RD)],
    "voice_out": [(C3 + NW, 542), (1245, 542)],
}
LABEL_AT = {"rm_rt": (325, 108), "rt_llm": (640, 96), "rt_cw": (880, 72), "rt_ddb": (600, 248), "rt_ath": (880, 312),
            "quick_rt": (325, 196), "dep_rt": (410, 308), "rm_ath": (200, 444), "voice_in": (170, 542),
            "trn_ddb": (705, 380), "ddb_pol": (860, 380), "voice_out": (1090, 542), "rt_mem": (520, 196), "kiro_dep": (325, 390)}

ALL = {n: (v[5], None) for n, v in NODES.items()}
SCENES = [
    ("1 · ROUTING MACHINE tetikler, ajanlar AgentCore'da karar verir",
     ["ROUTING MACHINE sabah gönderileri kümeler ve rotalar; zincir buradan başlar. Beş ajan Bedrock AgentCore Runtime'da çalışır,",
      "kararı Amazon Bedrock'taki Claude verir, sayıları araçlar hesaplar. Oturum AgentCore Memory'de, her adımın izi CloudWatch'ta."],
     ("Tetik → AgentCore → Claude", BLUE),
     {"rm_rt": (BLUE, 0.0, "plan + rota"), "rt_llm": (BLUE, 0.25, "karar"), "rt_mem": (BLUE, 0.45, "oturum"),
      "rt_cw": (RED, 0.6, "izler")},
     {"rm": (BLUE, "tetik"), "rt": (BLUE, None), "llm": (BLUE, None), "mem": (BLUE, None), "cw": (RED, None)}),
    ("2 · Hafıza ve veri: kalıcı adres bilgisi, salt okunur geçmiş",
     ["Adres bilgisi DynamoDB'de kalıcıdır: kurye değişse de bilgi adreste kalır. Geçmiş teslim verisi S3'te, Glue kataloğunda,",
      "Athena ile salt okunur SQL'le sorgulanır. IAM politikaları rolleri dar tutar (analiz salt okunur); kişisel veri yüklenmez."],
     ("DynamoDB · S3 + Glue + Athena · IAM", GREEN),
     {"rt_ddb": (GREEN, 0.0, "adres hafızası"), "rm_ath": (GREEN, 0.2, "geçmiş veri"), "rt_ath": (GREEN, 0.4, "salt okunur SQL")},
     {"rt": (BLUE, None), "ddb": (GREEN, None), "ath": (GREEN, None), "iam": (RED, "en az yetki"), "rm": (BLUE, None)}),
    ("3 · Sesli döngü: kurye konuşur, sistem dinler, kapıda söyler",
     ["Kurye notunu sesle bırakır; Transcribe metne çevirir, Hafıza Ajanı kişisel veriyi ayıklayıp DynamoDB'ye yazar.",
      "Sonraki kurye kapıya yaklaşınca Polly aynı bilgiyi doğal Türkçe sesle okur. Kurye ne yazar ne ekrana bakar."],
     ("Ses → metin → hafıza → ses", PURPLE),
     {"voice_in": (PURPLE, 0.0, "sesli not"), "trn_ddb": (PURPLE, 0.25, "metin → hafıza"), "ddb_pol": (PURPLE, 0.5, "kapı kartı"),
      "voice_out": (PURPLE, 0.7, "kapıda dinler")},
     {"trn": (PURPLE, None), "ddb": (GREEN, None), "pol": (PURPLE, None)}),
    ("4 · Amazon Quick: ekip sisteme doğal dille sorar",
     ["Amazon Quick, MCP üzerinden AgentCore Gateway'e bağlıdır: ekip panodan soru sorar, istek aynı ajanlara gider.",
      "Analiz Ajanı geçmişi Athena'da salt okunur sorgular; cevap Claude'un kararı, sayılar aracın hesabıdır."],
     ("Quick → MCP → AgentCore → Athena", TEAL),
     {"quick_rt": (TEAL, 0.0, "MCP"), "rt_llm": (BLUE, 0.3, None), "rt_ath": (GREEN, 0.45, "salt okunur SQL")},
     {"quick": (TEAL, None), "rt": (BLUE, None), "llm": (BLUE, None), "ath": (GREEN, None)}),
    ("5 · Geliştirme ve dağıtım: Kiro'dan AgentCore'a",
     ["Her özellik Kiro'da spec ile başlar (gereksinim → tasarım → görev); projenin MCP sunucusu şube hafızasını Kiro'ya açar.",
      "agentcore deploy, AWS CDK ile beş runtime'ı, hafızayı ve IAM politikalarını kodla kurar; aynı komut her ortamda aynı sonucu verir."],
     ("Kiro → CDK → AgentCore", AMBER),
     {"kiro_dep": (AMBER, 0.0, "spec + kod"), "dep_rt": (AMBER, 0.35, "kurar")},
     {"kiro": (AMBER, "önce spec"), "dep": (AMBER, None), "rt": (BLUE, None), "mem": (BLUE, None), "iam": (RED, None)}),
    ("Özet · hangi AWS servisi, neden",
     ["Tetik ROUTING MACHINE; karar Bedrock'ta Claude, çalışma AgentCore'da; adres hafızası DynamoDB'de, geçmiş Athena'da.",
      "Ses Transcribe ve Polly ile döner; izler CloudWatch'ta, yetki IAM'de; ekip Quick ile sorar, altyapı Kiro + CDK ile kurulur."],
     ("13 parça · her birinin bir nedeni var", BLUE),
     {e: (NODES[e.split("_")[0]][5] if e.split("_")[0] in NODES else PURPLE, 0.0, None) for e in EDGES},
     ALL),
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


def dashed_line(d, p, color, width, dash=7, gap=5):
    total, pos = sum(seg_len(p)), 0.0
    while pos < total:
        d.line([point_at(p, pos), point_at(p, min(pos + s(dash), total))], fill=color, width=s(width))
        pos += s(dash + gap)


def draw_poly(d, p, color, width, dashed=False, arrow=True):
    p = pts(p)
    if dashed:
        dashed_line(d, p, color, width)
    else:
        d.line(p, fill=color, width=s(width), joint="curve")
    if arrow:
        (x1, y1), (x2, y2) = p[-2], p[-1]
        a = math.atan2(y2 - y1, x2 - x1)
        L = s(8)
        d.polygon([(x2, y2), (x2 - L * math.cos(a - 0.45), y2 - L * math.sin(a - 0.45)),
                   (x2 - L * math.cos(a + 0.45), y2 - L * math.sin(a + 0.45))], fill=color)


def rect_outline(d, x1, y1, x2, y2, color, width, style):
    """Dashed or dotted rectangle outline (Pillow has no dash support)."""
    edges = [[(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)], [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)]]
    dash, gap = (7, 5) if style == "dashed" else (2, 4)
    for e in edges:
        dashed_line(d, pts(e), color, width, dash, gap)


def label_pos(name):
    if name in LABEL_AT:
        return LABEL_AT[name]
    p = EDGES[name]
    lens = seg_len(p)
    i = max(range(len(lens)), key=lambda j: lens[j])
    (x1, y1), (x2, y2) = p[i], p[i + 1]
    return ((x1 + x2) / 2, (y1 + y2) / 2 - 11)


def fit(d, txt, size, bold, maxw):
    """Largest font (down to 70 %) whose rendered width fits maxw."""
    f = font(size, bold)
    sz = size
    while d.textlength(txt, font=f) / K > maxw and sz > size * 0.7:
        sz -= 0.5
        f = font(sz, bold)
    return f


def text_c(d, xy, txt, f, fill):
    d.text((s(xy[0]), s(xy[1])), txt, font=f, fill=fill, anchor="mm")


def pill(d, cx, cy, txt, color, f=F_SMALL):
    w = d.textlength(txt, font=f) / K + 14
    d.rounded_rectangle([s(cx - w / 2), s(cy - 9), s(cx + w / 2), s(cy + 9)], radius=s(9), fill=color)
    text_c(d, (cx, cy), txt, f, BG)


def legend(d):
    x = 560
    for txt, col in (("ajan ve model", BLUE), ("veri ve hafıza", GREEN), ("ses", PURPLE)):
        d.rounded_rectangle([s(x), s(18), s(x + 12), s(30)], radius=s(3), fill=col)
        d.text((s(x + 18), s(24)), txt, font=F_SUB, fill=TEXT, anchor="lm")
        x += 34 + d.textlength(txt, font=F_SUB) / K
    x = 560
    for txt, col in (("izleme ve güvenlik", RED), ("erişim", TEAL), ("geliştirme", AMBER)):
        d.rounded_rectangle([s(x), s(40), s(x + 12), s(52)], radius=s(3), fill=col)
        d.text((s(x + 18), s(46)), txt, font=F_SUB, fill=TEXT, anchor="lm")
        x += 34 + d.textlength(txt, font=F_SUB) / K


def frame(scene, f):
    title, caption, badge, edges, nodes = scene
    t = f / SCENE_FRAMES
    img = Image.new("RGB", (s(W), s(H)), BG)
    d = ImageDraw.Draw(img)

    d.text((s(26), s(26)), "Courier Memory · AWS altyapısı", font=F_TITLE, fill=TEXT, anchor="lm")
    d.text((s(26), s(48)), "Hangi servis, ne iş, neden", font=F_SUB, fill=GREY, anchor="lm")
    legend(d)

    for x1, y1, x2, y2, lab, col in ZONES:
        d.rounded_rectangle([s(x1), s(y1), s(x2), s(y2)], radius=s(10), fill=mix(col, 0.05), outline=mix(col, 0.35), width=s(1))
        lw = d.textlength(lab, font=F_ZONE) / K + 12
        d.rounded_rectangle([s(x1 + 10), s(y1 - 7), s(x1 + 10 + lw), s(y1 + 7)], radius=s(6), fill=BG)
        d.text((s(x1 + 16), s(y1)), lab, font=F_ZONE, fill=mix(col, 0.9), anchor="lm")

    for name, p in EDGES.items():
        active = name in edges and t >= edges[name][1]
        draw_poly(d, p, edges[name][0] if active else DIM, 3 if active else 2)
    for name, (col, start, lab) in edges.items():
        if t < start:
            continue
        p = pts(EDGES[name])
        total = sum(seg_len(p))
        pos = ((f - start * SCENE_FRAMES) * s(5)) % s(40)
        while pos < total:
            x, y = point_at(p, pos)
            r = s(3.5)
            d.ellipse([x - r - s(3), y - r - s(3), x + r + s(3), y + r + s(3)], fill=mix(col, 0.35))
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
            pos += s(40)

    for key, (x, y, name, what, why, cat) in NODES.items():
        lit = key in nodes
        col, tag = nodes.get(key, (DIM, None))
        if lit:
            glow = 0.5 + 0.5 * math.sin(f / 5)
            d.rounded_rectangle([s(x - 4), s(y - 4), s(x + NW + 4), s(y + NH + 4)], radius=s(13),
                                outline=mix(col, 0.25 + 0.25 * glow), width=s(3))
        d.rounded_rectangle([s(x), s(y), s(x + NW), s(y + NH)], radius=s(9), fill=mix(col, 0.16, PANEL) if lit else PANEL,
                            outline=col if lit else DIM, width=s(2))
        d.rounded_rectangle([s(x), s(y), s(x + 6), s(y + NH)], radius=s(3), fill=cat if lit else mix(cat, 0.4))
        text_c(d, (x + NW / 2 + 3, y + 22), name, fit(d, name, 15, True, NW - 20), TEXT if lit else MUTED)
        text_c(d, (x + NW / 2 + 3, y + 45), what, fit(d, what, 12, False, NW - 18), (190, 202, 220) if lit else MUTED)
        text_c(d, (x + NW / 2 + 3, y + 65), why, fit(d, why, 11.5, True, NW - 18), WHY if lit else mix(WHY, 0.35))
        if tag:
            tw = d.textlength(tag, font=F_SMALL) / K + 14
            pill(d, x + NW - 6 - tw / 2, y - 1, tag, col)
    for name, (col, start, lab) in edges.items():
        if lab and t >= start:
            pill(d, *label_pos(name), lab, col)

    d.rounded_rectangle([s(16), s(658), s(W - 16), s(H - 12)], radius=s(12), fill=PANEL)
    d.text((s(36), s(683)), title, font=F_CAP_T, fill=TEXT, anchor="lm")
    btxt, bcol = badge
    bw = d.textlength(btxt, font=F_SMALL) / K + 24
    d.rounded_rectangle([s(W - 36 - bw), s(671), s(W - 36), s(695)], radius=s(12), fill=bcol)
    d.text((s(W - 36 - bw / 2), s(683)), btxt, font=F_SMALL, fill=BG, anchor="mm")
    for i, line in enumerate(caption):
        d.text((s(36), s(712 + i * 21)), line, font=fit(d, line, 14, False, W - 72), fill=(203, 213, 225), anchor="lm")
    for i in range(len(SCENES)):
        cx = W / 2 - (len(SCENES) - 1) * 9 + i * 18
        on = SCENES[i] is scene
        r = 4 if on else 3
        d.ellipse([s(cx - r), s(H - 5 - r), s(cx + r), s(H - 5 + r)], fill=TEXT if on else DIM)

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
