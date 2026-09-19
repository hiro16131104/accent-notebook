import pytest

from app import app


@pytest.fixture
def client():
    """Flask テストクライアントを生成する。"""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
