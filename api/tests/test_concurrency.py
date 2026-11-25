import os
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


def test_concurrent_first_requests(tmp_path):
    os.environ["CM_LLM_MODE"] = "mock"
    os.environ["CM_MEMORY_FILE"] = str(tmp_path / "mem.json")
    from api import main
    main.sv.cache_clear()
    c = TestClient(main.app)
    paths = ["/api/status", "/api/meta", "/api/summary", "/api/blocks", "/api/couriers", "/api/status"] * 3
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda p: c.get(p).status_code, paths))
    assert all(x == 200 for x in codes), codes


def test_corrupt_memory_file_recovers(tmp_path):
    os.environ["CM_LLM_MODE"] = "mock"
    f = tmp_path / "mem.json"
    f.write_text('{"app_data": true, "run_id": "x", "entries": [{"id": "M1", "add', encoding="utf-8")
    os.environ["CM_MEMORY_FILE"] = str(f)
    from api import main
    main.sv.cache_clear()
    c = TestClient(main.app)
    assert c.get("/api/status").status_code == 200
    assert c.get("/api/memory/summary?day=" + str(c.get("/api/meta").json()["critical"]["day"])).json()["total"] > 0
