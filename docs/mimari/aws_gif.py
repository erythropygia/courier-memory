"""Animated AWS infrastructure chart, kept simple: every service with what it does and WHY we use it.

Web entry (CloudFront → ALB → ECS Fargate), agents and model (7 domain agents in ECS, 5 agents in AgentCore),
data, voice, Amazon Quick / Kiro access over MCP, and delivery (GitHub Actions + CDK). Everything runs in us-east-1.
Companion to mimari_gif.py (same visual language).

Usage:  python docs/mimari/aws_gif.py   (needs Pillow; Arial from macOS, Windows or Linux msttcorefonts)
Output: docs/mimari/aws-altyapi.gif
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("aws-altyapi.gif")
K = 2                                   # supersampling factor
W, H = 1400, 800
FPS_MS = 90
SCENE_FRAMES = 48
OUT_W = 1120

_WIN_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
FONT_CANDIDATES = {
    False: [Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/Library/Fonts/Arial.ttf"),
            _WIN_FONTS / "arial.ttf", Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")],
    True: [Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"), Path("/Library/Fonts/Arial Bold.ttf"),
           _WIN_FONTS / "arialbd.ttf", Path("/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf"),
           Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")],
}
_fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font_path(bold: bool) -> Path:
    for p in FONT_CANDIDATES[bold]:
        if p.is_file():
            return p
    raise FileNotFoundError("Arial not found; tried: " + ", ".join(str(p) for p in FONT_CANDIDATES[bold]))


def font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (round(size * K), bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(font_path(bold)), key[0])
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

C1, C2, C3, C4, C5 = 14, 302, 590, 878, 1166     # column x
NW, NH = 218, 84
RA, RB, RC, RD = 92, 240, 388, 536               # row y
CAP_Y = H - 112                                  # caption panel top

# key: (x, y, name, what, why, category color)   (keys without "_": edge names are "<from>_<to>")
NODES = {
    # row A: delivery and model
    "gha": (C1, RA, "GitHub Actions · OIDC", "İmaj → ECR, ECS ve Lambda güncellenir", "Neden: kayıtlı gizli anahtar yok", AMBER),
    "ecr": (C2, RA, "Amazon ECR", "Web uygulamasının konteyner imajı", "Neden: her sürüm etiketli, geri dönülür", AMBER),
    "bed": (C3, RA, "Amazon Bedrock · Claude", "Sonnet 5: ajanların modeli", "Neden: karar modelde, sayı araçta", BLUE),
    "dep": (C4, RA, "agentcore deploy · AWS CDK", "CloudFormation: 5 runtime + hafıza", "Neden: altyapı kodla, tekrar kurulur", AMBER),
    "cw": (C5, RA, "Amazon CloudWatch", "Loglar ve OpenTelemetry izleri", "Neden: her ajan adımı izlenir", RED),
    # row B: request path
    "cf": (C1, RB, "Amazon CloudFront", "Tek HTTPS adres, tüm arayüzler", "Neden: mikrofon HTTPS ister", TEAL),
    "alb": (C2, RB, "Application Load Balancer", "Yalnız CloudFront'a açık", "Neden: doğrudan erişim kapalı", TEAL),
    "ecs": (C3, RB, "Amazon ECS · Fargate", "FastAPI + arayüzler + 7 alan ajanı", "Neden: sunucu yönetimi yok", BLUE),
    "rt": (C4, RB, "Bedrock AgentCore Runtime", "Yönetici + planlama, kurye, hafıza, analiz", "Neden: sunucusuz, oturumlar ayrı", BLUE),
    "mem": (C5, RB, "AgentCore Memory", "Konuşma hafızası, oturum başına", "Neden: ajan bağlamı unutmaz", BLUE),
    # row C: voice, data, bridge
    "trn": (C1, RC, "Amazon Transcribe", "Streaming: kuryenin sesli notu → metin", "Neden: kurye yazmadan not bırakır", PURPLE),
    "pol": (C2, RC, "Amazon Polly", "Neural ses Burcu, kapı kartını okur", "Neden: kurye ekrana bakmadan duyar", PURPLE),
    "ddb": (C3, RC, "Amazon DynamoDB", "courier-memory: adres, akış, kullanım", "Neden: web ve 5 runtime aynı hafıza", GREEN),
    "lam": (C4, RC, "AWS Lambda · köprü", "Gateway aracını Supervisor'a iletir", "Neden: yalnız Supervisor'ı çağırır", TEAL),
    "ath": (C5, RC, "Amazon S3 + Glue + Athena", "Geçmiş teslim verisi, 4 tablo", "Neden: salt okunur SQL, 100 MB sınır", GREEN),
    # row D: outside access and security
    "kiro": (C1, RD, "Kiro", "Spec → tasarım → görev; MCP proxy", "Neden: önce spec, sonra kod", AMBER),
    "cog": (C2, RD, "Amazon Cognito", "OAuth client credentials token", "Neden: Gateway yalnız token kabul eder", TEAL),
    "quick": (C3, RD, "Amazon Quick", "Sohbet ajanı + MCP bağlayıcı", "Neden: ekip doğal dille sorar", TEAL),
    "gw": (C4, RD, "AgentCore Gateway", "MCP uç noktası: ask_courier_memory", "Neden: Quick ve Kiro tek kapıdan", TEAL),
    "iam": (C5, RD, "AWS IAM · en az yetki", "Rol başına dar izin: model, tablo, ses", "Neden: analiz salt okunur", RED),
}

ZONES = [  # (x1, y1, x2, y2, label, color)
    (6, 380, 528, 480, "Sesli döngü", PURPLE),
    (6, 528, 1104, 628, "Dış erişim · MCP", TEAL),
]

EDGES = {
    "gha_ecr": [(C1 + NW, 134), (C2, 134)],
    "gha_dep": [(123, RA), (123, 74), (987, 74), (987, RA)],
    "ecr_ecs": [(411, RA + NH), (411, 208), (640, 208), (640, RB)],
    "ecs_bed": [(699, RB), (699, RA + NH)],
    "rt_bed": [(930, RB), (930, 208), (760, 208), (760, RA + NH)],
    "dep_rt": [(987, RA + NH), (987, RB)],
    "rt_cw": [(1030, RB), (1030, 208), (1240, 208), (1240, RA + NH)],
    "cf_alb": [(C1 + NW, 282), (C2, 282)],
    "alb_ecs": [(C2 + NW, 282), (C3, 282)],
    "ecs_rt": [(C3 + NW, 282), (C4, 282)],
    "rt_mem": [(C4 + NW, 282), (C5, 282)],
    "ecs_trn": [(610, RB + NH), (610, 340), (160, 340), (160, RC)],
    "ecs_pol": [(640, RB + NH), (640, 356), (450, 356), (450, RC)],
    "ecs_ddb": [(730, RB + NH), (730, RC)],
    "rt_ddb": [(920, RB + NH), (920, 344), (795, 344), (795, RC)],
    "lam_rt": [(987, RC), (987, RB + NH)],
    "rt_ath": [(1060, RB + NH), (1060, 356), (1240, 356), (1240, RC)],
    "gw_lam": [(987, RD), (987, RC + NH)],
    "quick_gw": [(C3 + NW, 578), (C4, 578)],
    "cog_quick": [(C2 + NW, 578), (C3, 578)],
    "kiro_gw": [(123, RD + NH), (123, 646), (950, 646), (950, RD + NH)],
}
LABEL_AT = {"gha_ecr": (267, 134), "gha_dep": (555, 74), "ecr_ecs": (525, 208), "ecs_bed": (699, 208),
            "rt_bed": (845, 208), "dep_rt": (987, 208), "rt_cw": (1135, 208), "cf_alb": (267, 282),
            "alb_ecs": (555, 282), "ecs_rt": (843, 282), "rt_mem": (1131, 282), "ecs_trn": (400, 340),
            "ecs_pol": (545, 356), "ecs_ddb": (730, 362), "rt_ddb": (858, 344), "lam_rt": (987, 356),
            "rt_ath": (1150, 356), "gw_lam": (987, 504), "quick_gw": (843, 578), "cog_quick": (555, 578),
            "kiro_gw": (330, 646)}

ALL = {n: (v[5], None) for n, v in NODES.items()}
SCENES = [
    ("1 · Web girişi ve barındırma: CloudFront → ALB → ECS Fargate",
     ["Kurye ekranı ve sunum ekranı tek HTTPS adresten girer: Amazon CloudFront (mikrofon HTTPS ister) → yalnız CloudFront'a açık Application Load Balancer.",
      "ECS Fargate'te FastAPI ve arayüzler çalışır (hikâye, canlı zincir, eski ekran, demo); konteyner imajı Amazon ECR'dan gelir, sunucu yönetilmez."],
     ("CloudFront → ALB → ECS · ECR", TEAL),
     {"cf_alb": (TEAL, 0.0, "HTTPS"), "alb_ecs": (TEAL, 0.2, "yönlendir"), "ecr_ecs": (AMBER, 0.45, "imaj")},
     {"cf": (TEAL, "HTTPS"), "alb": (TEAL, "yalnız CloudFront"), "ecs": (BLUE, "web uygulaması"), "ecr": (AMBER, None)}),
    ("2 · Ajanlar ve model: ECS'te 7 alan ajanı, AgentCore'da 5 ajan",
     ["Web uygulaması 7 alan ajanını (Orkestratör, Atama, Hafıza, Brifing, Hasat, Değerlendirme, Bölge) Bedrock'taki Claude Sonnet 5 ile canlı çalıştırır;",
      "canlı zincir sunum ekranından başlar (8 adım, Acil Durum Kapısı dahil). \"AgentCore zinciri\" aynı işi AgentCore'daki 5 ajana yaptırır; oturum Memory'de, izler CloudWatch'ta."],
     ("ECS 7 ajan · AgentCore 5 ajan · Claude", BLUE),
     {"ecs_bed": (BLUE, 0.0, "7 ajan · canlı"), "ecs_rt": (BLUE, 0.2, "zincir"), "rt_bed": (BLUE, 0.35, "karar"),
      "rt_mem": (BLUE, 0.5, "oturum"), "rt_cw": (RED, 0.6, "izler")},
     {"ecs": (BLUE, "7 alan ajanı"), "rt": (BLUE, "5 ajan"), "bed": (BLUE, "Sonnet 5"), "mem": (BLUE, None), "cw": (RED, None)}),
    ("3 · Veri ve hafıza: ortak DynamoDB tablosu, salt okunur Athena",
     ["DynamoDB'deki courier-memory tablosu canlı adres hafızasını, ajan akışını ve kullanımı tutar; web uygulaması ve 5 runtime aynı tabloyu kullanır.",
      "Geçmiş teslim verisi S3'te, Glue kataloğunda 4 tablo; Analiz Ajanı Athena'da salt okunur SQL çalıştırır (sorgu başına 100 MB). IAM her rolü dar tutar."],
     ("DynamoDB · S3 + Glue + Athena · IAM", GREEN),
     {"ecs_ddb": (GREEN, 0.0, "adres hafızası"), "rt_ddb": (GREEN, 0.2, "aynı tablo"), "rt_ath": (GREEN, 0.4, "salt okunur SQL")},
     {"ecs": (BLUE, None), "rt": (BLUE, None), "ddb": (GREEN, None), "ath": (GREEN, "4 tablo"), "iam": (RED, "en az yetki")}),
    ("4 · Sesli döngü: kurye konuşur, sistem dinler, kapıda söyler",
     ["Kurye notunu sesle bırakır: ses HTTPS üzerinden web uygulamasına akar, Amazon Transcribe Streaming (tr-TR) metne çevirir, Hafıza Ajanı DynamoDB'ye yazar.",
      "Sonraki kurye kapıya yaklaşınca Amazon Polly kapı kartını neural Türkçe sesle (Burcu) okur. Kurye ne yazar ne ekrana bakar."],
     ("Ses · metin · hafıza · ses", PURPLE),
     {"cf_alb": (TEAL, 0.0, None), "alb_ecs": (TEAL, 0.0, None), "ecs_trn": (PURPLE, 0.15, "sesli not"),
      "ecs_ddb": (GREEN, 0.4, "not → hafıza"), "ecs_pol": (PURPLE, 0.6, "kart metni")},
     {"cf": (TEAL, "HTTPS"), "ecs": (BLUE, None), "trn": (PURPLE, "tr-TR"), "pol": (PURPLE, "Burcu"), "ddb": (GREEN, None)}),
    ("5 · Amazon Quick ve Kiro: MCP ile aynı ajanlara erişim",
     ["Amazon Quick'teki sohbet ajanı MCP bağlayıcısıyla gelir: Amazon Cognito'dan OAuth token alır (client credentials), AgentCore Gateway'e bağlanır.",
      "Gateway aracı AWS Lambda köprüsünü çağırır, köprü soruyu Supervisor'a (yönetici ajan) iletir. Kiro aynı Gateway'i yerel MCP proxy ile kullanır."],
     ("Quick → Gateway → Lambda → Supervisor", TEAL),
     {"cog_quick": (TEAL, 0.0, "token"), "quick_gw": (TEAL, 0.15, "MCP"), "kiro_gw": (AMBER, 0.3, "yerel MCP proxy"),
      "gw_lam": (TEAL, 0.45, "araç"), "lam_rt": (TEAL, 0.6, "iletir")},
     {"quick": (TEAL, None), "cog": (TEAL, None), "gw": (TEAL, None), "lam": (TEAL, None), "kiro": (AMBER, None),
      "rt": (BLUE, "Supervisor")}),
    ("6 · Geliştirme ve teslimat: Kiro'da spec, GitHub Actions ile dağıtım",
     ["Her özellik Kiro'da spec ile başlar (gereksinim → tasarım → görev). main'e gelen değişiklikte GitHub Actions OIDC ile IAM rolü üstlenir, gizli anahtar tutmaz.",
      "Web imajı ECR'a gider ve ECS servisi güncellenir; agentcore deploy AWS CDK / CloudFormation ile 5 runtime'ı ve hafızayı kurar; köprü Lambda kodu da güncellenir."],
     ("Kiro → GitHub Actions → ECR · ECS · AgentCore", AMBER),
     {"gha_ecr": (AMBER, 0.0, "imaj"), "ecr_ecs": (AMBER, 0.2, "yeni sürüm"), "gha_dep": (AMBER, 0.35, "agentcore deploy"),
      "dep_rt": (AMBER, 0.55, "kurar")},
     {"kiro": (AMBER, "önce spec"), "gha": (AMBER, "OIDC"), "ecr": (AMBER, None), "dep": (AMBER, None), "ecs": (BLUE, None),
      "rt": (BLUE, None), "iam": (RED, "OIDC rolü")}),
    ("Özet · hangi AWS servisi, neden",
     ["Giriş CloudFront + ALB; uygulama ve 7 alan ajanı ECS Fargate'te; 5 ajan AgentCore Runtime'da; karar Bedrock'ta Claude; hafıza DynamoDB ve AgentCore Memory'de.",
      "Geçmiş Athena'da; ses Transcribe ve Polly ile döner; izler CloudWatch'ta, yetki IAM'de; Quick ve Kiro MCP ile bağlanır; teslimat GitHub Actions + CDK."],
     (f"{len(NODES)} parça · her birinin bir nedeni var", BLUE),
     {e: (NODES[e.split("_")[0]][5], 0.0, None) for e in EDGES},
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
    rows = ((("ajan ve model", BLUE), ("veri ve hafıza", GREEN), ("ses", PURPLE)),
            (("izleme ve güvenlik", RED), ("erişim", TEAL), ("geliştirme ve teslimat", AMBER)))
    for y, row in zip((24, 46), rows):
        x = 640
        for txt, col in row:
            d.rounded_rectangle([s(x), s(y - 6), s(x + 12), s(y + 6)], radius=s(3), fill=col)
            d.text((s(x + 18), s(y)), txt, font=F_SUB, fill=TEXT, anchor="lm")
            x += 34 + d.textlength(txt, font=F_SUB) / K


def draw_zones(d):
    for x1, y1, x2, y2, lab, col in ZONES:
        d.rounded_rectangle([s(x1), s(y1), s(x2), s(y2)], radius=s(10), fill=mix(col, 0.05), outline=mix(col, 0.35), width=s(1))
        lw = d.textlength(lab, font=F_ZONE) / K + 12
        d.rounded_rectangle([s(x1 + 10), s(y1 - 7), s(x1 + 10 + lw), s(y1 + 7)], radius=s(6), fill=BG)
        d.text((s(x1 + 16), s(y1)), lab, font=F_ZONE, fill=mix(col, 0.9), anchor="lm")


def draw_edges(d, edges, f, t):
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


def draw_nodes(d, nodes, f):
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


def draw_caption(d, scene):
    title, caption, (btxt, bcol) = scene[0], scene[1], scene[2]
    d.rounded_rectangle([s(16), s(CAP_Y), s(W - 16), s(H - 12)], radius=s(12), fill=PANEL)
    d.text((s(36), s(CAP_Y + 25)), title, font=F_CAP_T, fill=TEXT, anchor="lm")
    bw = d.textlength(btxt, font=F_SMALL) / K + 24
    d.rounded_rectangle([s(W - 36 - bw), s(CAP_Y + 13), s(W - 36), s(CAP_Y + 37)], radius=s(12), fill=bcol)
    d.text((s(W - 36 - bw / 2), s(CAP_Y + 25)), btxt, font=F_SMALL, fill=BG, anchor="mm")
    for i, line in enumerate(caption):
        d.text((s(36), s(CAP_Y + 54 + i * 21)), line, font=fit(d, line, 14, False, W - 72), fill=(203, 213, 225), anchor="lm")
    for i in range(len(SCENES)):
        cx = W / 2 - (len(SCENES) - 1) * 9 + i * 18
        on = SCENES[i] is scene
        r = 4 if on else 3
        d.ellipse([s(cx - r), s(H - 5 - r), s(cx + r), s(H - 5 + r)], fill=TEXT if on else DIM)


def frame(scene, f):
    edges, nodes = scene[3], scene[4]
    t = f / SCENE_FRAMES
    img = Image.new("RGB", (s(W), s(H)), BG)
    d = ImageDraw.Draw(img)

    d.text((s(26), s(26)), "Courier Memory · AWS altyapısı", font=F_TITLE, fill=TEXT, anchor="lm")
    d.text((s(26), s(48)), "Hangi servis, ne iş, neden · hepsi us-east-1", font=F_SUB, fill=GREY, anchor="lm")
    legend(d)
    draw_zones(d)
    draw_edges(d, edges, f, t)
    draw_nodes(d, nodes, f)
    for name, (col, start, lab) in edges.items():
        if lab and t >= start:
            pill(d, *label_pos(name), lab, col)
    draw_caption(d, scene)
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
