from fastapi.testclient import TestClient


def test_health_creates_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEDULER_DATA_DIR", str(tmp_path))
    from app.main import app

    with TestClient(app) as client:
        res = client.get("/api/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "schema_version": "1"}
    assert (tmp_path / "scheduler.db").exists()
