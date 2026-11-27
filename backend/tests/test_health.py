def test_health_creates_db(client, tmp_path):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "schema_version": "1"}
    assert (tmp_path / "scheduler.db").exists()
