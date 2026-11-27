import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEDULER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHEDULER_NO_MAIL_SYNC", "1")
    from app.main import app

    with TestClient(app) as c:
        yield c
