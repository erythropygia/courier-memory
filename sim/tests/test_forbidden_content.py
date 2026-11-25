"""Repoya gerçek veri ya da şirket içi ad girmesini yakalar. Kalıplar parçalanmış dizgilerle kurulur."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
SKIP_DIRS = {".kiro", ".venv", "runs", ".git", "__pycache__", ".pytest_cache", "node_modules", "courier_memory.egg-info"}
TEXT_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".html", ".js", ".css", ".txt", ".toml", ".sh", ".ps1"}

PATTERNS = [
    r"\b" + "AR" + "P" + r"\b",
    r"\b" + "Cro" + "wd" + r"\b",
    "Cro" + "wdDB",
    "Arp" + "Schedule",
    "External" + "Cluster",
    "External" + "Route",
    "aras" + "kargo" + r"\.com\.tr",
    "map" + "-cls",
    r"\b" + "BK" + "Z" + r"\d{2}\b",
]
# Sayısal kalıplar üretilmiş veride (adres/gün numaraları) rastlantısal eşleşir; yalnız kod ve belgelerde aranır.
NUMERIC_PATTERNS = [r"\b" + "66" + "78" + r"\b"]
GENERATED_DIRS = {"data", "cassettes"}


def test_no_forbidden_content():
    rx = [re.compile(p) for p in PATTERNS]
    rx_num = [re.compile(p) for p in NUMERIC_PATTERNS]
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.resolve() == SELF or p.suffix not in TEXT_EXT:
            continue
        parts = p.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        active = rx if parts[0] in GENERATED_DIRS else rx + rx_num
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for r in active:
                if r.search(line):
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {r.pattern}")
    assert not hits, "Yasaklı içerik bulundu:\n" + "\n".join(hits[:50])
