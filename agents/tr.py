"""Türkçe biçim yardımcıları."""

# Kod İngilizce, kullanıcıya giden cümle Türkçe: cümleye giren kodların etiketleri.
LEVEL_TR = {"low": "düşük", "mid": "orta", "high": "yüksek"}
DENSITY_TR = {"busy": "yoğun", "low": "düşük", "usual": "olağan"}
REASON_TR = {"recipient_absent": "alıcı yok", "address_not_found": "adres bulunamadı", "closed": "kapalı",
             "entry_failed": "giriş yapılamadı", "recipient_unreachable": "alıcıya ulaşılamadı",
             "wrong_deferral": "yanlış erteleme", "other": "diğer"}


def dative(n: int) -> str:
    """Sayıya yönelme eki: 3'e, 6'ya, 10'a, 20'ye."""
    n = abs(int(n))
    last = n % 10
    if last:
        return {1: "'e", 2: "'ye", 3: "'e", 4: "'e", 5: "'e", 6: "'ya", 7: "'ye", 8: "'e", 9: "'a"}[last]
    tens = (n // 10) % 10
    if tens:
        return {1: "'a", 2: "'ye", 3: "'a", 4: "'a", 5: "'ye", 6: "'a", 7: "'e", 8: "'e", 9: "'a"}[tens]
    return "'e" if n >= 100 else "'a"


def pct(x: float, nd: int = 1) -> str:
    return f"%{100 * x:.{nd}f}".replace(".", ",")


def hhmm(minute: float) -> str:
    m = int(round(minute))
    return f"{m // 60:02d}:{m % 60:02d}"


def num(x: float, nd: int = 1, sign: bool = False) -> str:
    """Türkçe sayı: 1.234,5 ve isteğe bağlı işaret."""
    s = f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def name_dative(name: str) -> str:
    """Özel ada yönelme eki (ünlü uyumu): Gökhan'a, Melis'e, Onur'a, Deniz'e, Ayşe'ye."""
    vowels = [ch for ch in name.lower() if ch in "aeıioöuü"]
    back = bool(vowels) and vowels[-1] in "aıou"
    ends_vowel = name[-1:].lower() in "aeıioöuü"
    return name + ("'" + ("y" if ends_vowel else "") + ("a" if back else "e"))
