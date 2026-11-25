"""Athena kurulumu: veri → JSON Lines dönüşümü ve tablo tanımları. AWS'ye gitmez."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athena_setup import TABLES, build_rows, create_table_sql  # noqa: E402

RUN = Path(__file__).resolve().parents[3] / "data" / "demo_run"


def test_every_table_builds_rows_matching_its_columns():
    for name, spec in TABLES.items():
        rows = list(build_rows(name, RUN))
        assert rows, name
        cols = [c for c, _ in spec["columns"]]
        assert all(list(r) == cols for r in rows[:50]), name
        assert all(json.dumps(r, ensure_ascii=False) for r in rows[:50])


def test_row_counts_and_content():
    assert sum(1 for _ in build_rows("deliveries", RUN)) == 92381
    assert sum(1 for _ in build_rows("addresses", RUN)) == 40000
    daily = list(build_rows("daily_metrics", RUN))
    assert {r["arm"] for r in daily} == {"A", "B", "C", "D"} and all(r["arm_label"] for r in daily)
    d = daily[0]
    assert d["fail"] == sum(v for k, v in d.items() if k.startswith("fail_"))       # nedenler toplamı = başarısız


def test_no_personal_data_leaves_the_repo():
    couriers = list(build_rows("couriers", RUN))
    assert couriers and all("name" not in r for r in couriers)
    assert "notes" not in TABLES                                                     # serbest metin notlar yüklenmez


def test_create_table_sql_points_to_table_prefix():
    sql = create_table_sql("deliveries", "courier_memory", "my-bucket")
    assert sql.startswith("CREATE EXTERNAL TABLE IF NOT EXISTS courier_memory.deliveries (")
    assert "`day` int" in sql and "org.openx.data.jsonserde.JsonSerDe" in sql
    assert sql.rstrip().endswith("LOCATION 's3://my-bucket/data/deliveries/'")
