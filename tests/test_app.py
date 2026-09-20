from tests.conftest import moras_for


def test_index_redirects_to_login_when_not_authenticated(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_index_returns_200_when_authenticated(client):
    with client.session_transaction() as sess:
        sess["user"] = {"sub": "1", "email": "user@example.com", "name": "Test User"}
    resp = client.get("/")
    assert resp.status_code == 200


def test_login_page_returns_200(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_api_words_requires_login(client):
    resp = client.get("/api/words")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_api_create_and_list_word(logged_in_client, dynamodb_table):
    reading = "てすと"
    payload = {
        "word": "テスト",
        "reading": reading,
        "note": "メモ",
        "moras": moras_for(reading),
    }
    create_resp = logged_in_client.post("/api/words", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.get_json()
    assert created["word"] == "テスト"

    list_resp = logged_in_client.get("/api/words")
    assert list_resp.status_code == 200
    assert [item["word_id"] for item in list_resp.get_json()] == [created["word_id"]]


def test_api_create_word_with_final_drop(logged_in_client, dynamodb_table):
    reading = "てすと"
    moras = moras_for(reading)
    moras[-1]["pitch"] = "H"
    payload = {
        "word": "テスト",
        "reading": reading,
        "note": "",
        "moras": moras,
        "final_drop": True,
    }
    resp = logged_in_client.post("/api/words", json=payload)
    assert resp.status_code == 201
    assert resp.get_json()["final_drop"] is True


def test_api_create_word_rejects_invalid_final_drop(logged_in_client, dynamodb_table):
    reading = "てすと"
    payload = {
        "word": "テスト",
        "reading": reading,
        "note": "",
        "moras": moras_for(reading),
        "final_drop": "yes",
    }
    resp = logged_in_client.post("/api/words", json=payload)
    assert resp.status_code == 400


def test_api_create_word_rejects_invalid_reading(logged_in_client, dynamodb_table):
    payload = {"word": "テスト", "reading": "テスト", "note": "", "moras": []}
    resp = logged_in_client.post("/api/words", json=payload)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_update_word(logged_in_client, dynamodb_table):
    reading = "てすと"
    created = logged_in_client.post(
        "/api/words",
        json={
            "word": "テスト",
            "reading": reading,
            "note": "",
            "moras": moras_for(reading),
        },
    ).get_json()

    new_reading = "しけん"
    update_resp = logged_in_client.put(
        f"/api/words/{created['word_id']}",
        json={
            "word": "試験",
            "reading": new_reading,
            "note": "",
            "moras": moras_for(new_reading),
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["word"] == "試験"


def test_api_update_word_not_found(logged_in_client, dynamodb_table):
    resp = logged_in_client.put(
        "/api/words/missing-id",
        json={
            "word": "テスト",
            "reading": "てすと",
            "note": "",
            "moras": moras_for("てすと"),
        },
    )
    assert resp.status_code == 404


def test_api_delete_word(logged_in_client, dynamodb_table):
    reading = "てすと"
    created = logged_in_client.post(
        "/api/words",
        json={
            "word": "テスト",
            "reading": reading,
            "note": "",
            "moras": moras_for(reading),
        },
    ).get_json()

    delete_resp = logged_in_client.delete(f"/api/words/{created['word_id']}")
    assert delete_resp.status_code == 204
    assert logged_in_client.get("/api/words").get_json() == []


def test_api_set_bookmark(logged_in_client, dynamodb_table):
    reading = "てすと"
    created = logged_in_client.post(
        "/api/words",
        json={
            "word": "テスト",
            "reading": reading,
            "note": "",
            "moras": moras_for(reading),
        },
    ).get_json()

    resp = logged_in_client.patch(
        f"/api/words/{created['word_id']}/bookmark", json={"bookmarked": True}
    )
    assert resp.status_code == 200
    assert resp.get_json()["bookmarked"] is True


def test_api_set_bookmark_not_found(logged_in_client, dynamodb_table):
    resp = logged_in_client.patch(
        "/api/words/missing-id/bookmark", json={"bookmarked": True}
    )
    assert resp.status_code == 404


def test_api_create_word_rejects_non_json_content_type(
    logged_in_client, dynamodb_table
):
    resp = logged_in_client.post(
        "/api/words",
        data="word=テスト&reading=てすと",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


def test_api_create_word_rejects_too_long_word(logged_in_client, dynamodb_table):
    reading = "てすと"
    resp = logged_in_client.post(
        "/api/words",
        json={
            "word": "あ" * 101,
            "reading": reading,
            "note": "",
            "moras": moras_for(reading),
        },
    )
    assert resp.status_code == 400


def test_hsts_header_present_when_not_dev(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "APP_ENV", "prod")
    resp = client.get("/login")
    assert "Strict-Transport-Security" in resp.headers


def test_hsts_header_absent_in_dev(client):
    resp = client.get("/login")
    assert "Strict-Transport-Security" not in resp.headers


def test_login_page_script_nonce_matches_csp_header(client):
    resp = client.get("/login")
    csp = resp.headers["Content-Security-Policy"]
    nonce = csp.split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in resp.get_data(as_text=True)


def test_api_words_isolated_per_user(client, dynamodb_table):
    reading = "てすと"
    with client.session_transaction() as sess:
        sess["user"] = {"sub": "user-a", "email": "a@example.com", "name": "A"}
    client.post(
        "/api/words",
        json={
            "word": "テスト",
            "reading": reading,
            "note": "",
            "moras": moras_for(reading),
        },
    )

    with client.session_transaction() as sess:
        sess["user"] = {"sub": "user-b", "email": "b@example.com", "name": "B"}
    assert client.get("/api/words").get_json() == []
