"""KVKK koruması: hafıza kişiyi değil adresi ve binayı anlatır.

Araç düzeyinde son savunma hattı: hafızaya yazılacak metin burada denetlenir. Model ayıklamayı unutursa
araç yazmayı reddeder ve modelden metni yeniden yazmasını ister.
"""
from __future__ import annotations

import re

PHONE = re.compile(r"(\+?90[\s-]?)?0?\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
HONORIFIC_NAME = re.compile(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)\s+(hanım|hanim|bey|abla|abi|teyze|amca)\b", re.IGNORECASE)
JUDGEMENT = re.compile(
    r"\b(huysuz|tuhaf|deli|kaba|sinirli|yaşlı|yasli|hasta|engelli|sarhoş|sarhos|garip|cimri|kötü adam|teyze|amca)\b",
    re.IGNORECASE)
HEALTH_AGE = re.compile(r"\b(hasta|yaşlı|yasli|hamile|engelli|duymuyor|görmüyor|yatalak)\b", re.IGNORECASE)
# kapı/bina şifresi hafızaya yazılmaz. Kişisel veri değil ama güvenlik bilgisidir; sızarsa binaya erişim verir.
SECRET = re.compile(r"(şifre|sifre|parola|kap[ıi] kodu|giri[şs] kodu|alarm kodu|bina kodu|\bpin\b|\bkod(?:u|unu)?\s*[:=]?\s*\d{3,})",
                    re.IGNORECASE)


def find_pii(text: str) -> list[str]:
    """Metindeki kişisel veri parçalarını döndürür (boşsa temiz)."""
    hits: list[str] = []
    for rx in (PHONE, HONORIFIC_NAME, JUDGEMENT, HEALTH_AGE):
        for m in rx.finditer(text or ""):
            s = m.group(0).strip()
            if s and s not in hits:
                hits.append(s)
    return hits


def redact(text: str) -> str:
    """Kişisel veriyi metinden çıkarır (mock yolu ve son savunma)."""
    t = PHONE.sub("", text or "")
    t = HONORIFIC_NAME.sub("", t)
    # yargı/sağlık sözcüğü içeren cümle parçasını tümden at
    parts = re.split(r"[,.;]", t)
    keep = [p for p in parts if not (JUDGEMENT.search(p) or HEALTH_AGE.search(p))]
    t = ", ".join(p.strip() for p in keep if p.strip())
    return re.sub(r"\s{2,}", " ", t).strip(" ,")


def find_secret(text: str) -> list[str]:
    """Kapı/bina şifresi, giriş kodu gibi güvenlik bilgisi parçaları (boşsa temiz)."""
    return [m.group(0).strip() for m in SECRET.finditer(text or "")]


def redact_secret(text: str) -> str:
    """Şifre/kod geçen cümle parçasını tümden atar (kod sayısı ayrı parçada kalmasın diye parçanın tamamı)."""
    parts = re.split(r"[,.;]", text or "")
    keep = [p for p in parts if not SECRET.search(p)]
    return re.sub(r"\s{2,}", " ", ", ".join(p.strip() for p in keep if p.strip())).strip(" ,")
