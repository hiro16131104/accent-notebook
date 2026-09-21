import logging

from libs import words_store


def _messages(caplog):
    return [record.getMessage() for record in caplog.records]


def test_request_is_logged_with_status_and_user(logged_in_client, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        logged_in_client.get("/")
    assert any("GET / -> 200" in m and "user=user-1" in m for m in _messages(caplog))


def test_anonymous_request_is_logged_without_user(client, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        client.get("/login")
    assert any("GET /login -> 200" in m and "user=-" in m for m in _messages(caplog))


def test_client_error_is_logged_as_warning(client, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        client.post("/auth/google/callback")
    records = [r for r in caplog.records if "-> 4" in r.getMessage()]
    assert records
    assert all(r.levelno == logging.WARNING for r in records)


def test_unhandled_exception_returns_json_500_and_logs_traceback(
    logged_in_client, caplog, monkeypatch
):
    def boom(user_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(words_store, "list_words", boom)
    with caplog.at_level(logging.INFO, logger="app"):
        resp = logged_in_client.get("/api/words")

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "サーバーエラーが発生しました。"}
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    # 例外のスタックトレースと、500 のリクエストログの両方が出る
    assert any(r.exc_info and "未処理の例外" in r.getMessage() for r in error_records)
    assert any("GET /api/words -> 500" in r.getMessage() for r in error_records)


def test_unhandled_exception_on_page_returns_plain_500(
    logged_in_client, caplog, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.render_template", boom)
    resp = logged_in_client.get("/")
    assert resp.status_code == 500
    assert "サーバーエラー" in resp.get_data(as_text=True)
