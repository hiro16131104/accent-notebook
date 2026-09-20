import pytest

from libs import words_store
from tests.conftest import moras_for


def test_create_word_returns_item(dynamodb_table):
    reading = "てすと"
    item = words_store.create_word(
        "user-1", "テスト", reading, "メモ", moras_for(reading)
    )
    assert item["word"] == "テスト"
    assert item["reading"] == reading
    assert item["moras"] == moras_for(reading)
    assert item["bookmarked"] is False
    assert item["user_id"] == "user-1"


def test_create_word_requires_word_and_reading(dynamodb_table):
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "", "てすと", "", moras_for("てすと"))
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "テスト", "", "", [])


def test_create_word_rejects_non_hiragana_reading(dynamodb_table):
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "テスト", "テスト", "", [])


def test_create_word_rejects_duplicate(dynamodb_table):
    reading = "てすと"
    words_store.create_word("user-1", "テスト", reading, "", moras_for(reading))
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "テスト", reading, "", moras_for(reading))


def test_create_word_allows_same_word_reading_for_different_user(dynamodb_table):
    reading = "てすと"
    words_store.create_word("user-1", "テスト", reading, "", moras_for(reading))
    item = words_store.create_word("user-2", "テスト", reading, "", moras_for(reading))
    assert item["user_id"] == "user-2"


def test_create_word_rejects_mora_count_mismatch(dynamodb_table):
    with pytest.raises(words_store.ValidationError):
        words_store.create_word(
            "user-1", "テスト", "てすと", "", [{"text": "て", "pitch": "L"}]
        )


def test_create_word_rejects_word_too_long(dynamodb_table):
    reading = "てすと"
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "あ" * 101, reading, "", moras_for(reading))


def test_create_word_rejects_note_too_long(dynamodb_table):
    reading = "てすと"
    with pytest.raises(words_store.ValidationError):
        words_store.create_word(
            "user-1", "テスト", reading, "あ" * 1001, moras_for(reading)
        )


def test_create_word_rejects_invalid_pitch(dynamodb_table):
    reading = "てすと"
    bad_moras = moras_for(reading)
    bad_moras[0]["pitch"] = "X"
    with pytest.raises(words_store.ValidationError):
        words_store.create_word("user-1", "テスト", reading, "", bad_moras)


def _moras_with_last_high(reading):
    moras = moras_for(reading)
    moras[-1]["pitch"] = "H"
    return moras


def test_create_word_defaults_final_drop_to_false(dynamodb_table):
    reading = "てすと"
    item = words_store.create_word(
        "user-1", "テスト", reading, "", _moras_with_last_high(reading)
    )
    assert item["final_drop"] is False


def test_create_word_stores_final_drop(dynamodb_table):
    reading = "てすと"
    item = words_store.create_word(
        "user-1",
        "テスト",
        reading,
        "",
        _moras_with_last_high(reading),
        final_drop=True,
    )
    assert item["final_drop"] is True
    assert words_store.list_words("user-1")[0]["final_drop"] is True


def test_create_word_ignores_final_drop_when_last_mora_is_low(dynamodb_table):
    reading = "てすと"
    item = words_store.create_word(
        "user-1", "テスト", reading, "", moras_for(reading), final_drop=True
    )
    assert item["final_drop"] is False


def test_create_word_rejects_non_bool_final_drop(dynamodb_table):
    reading = "てすと"
    with pytest.raises(words_store.ValidationError):
        words_store.create_word(
            "user-1",
            "テスト",
            reading,
            "",
            _moras_with_last_high(reading),
            final_drop="true",
        )


def test_update_word_changes_final_drop(dynamodb_table):
    reading = "てすと"
    created = words_store.create_word(
        "user-1", "テスト", reading, "", _moras_with_last_high(reading)
    )
    updated = words_store.update_word(
        "user-1",
        created["word_id"],
        "テスト",
        reading,
        "",
        _moras_with_last_high(reading),
        final_drop=True,
    )
    assert updated["final_drop"] is True


def test_update_word_not_found(dynamodb_table):
    with pytest.raises(words_store.NotFoundError):
        words_store.update_word(
            "user-1", "missing-id", "テスト", "てすと", "", moras_for("てすと")
        )


def test_update_word_changes_fields(dynamodb_table):
    reading = "てすと"
    created = words_store.create_word(
        "user-1", "テスト", reading, "", moras_for(reading)
    )
    new_reading = "しけん"
    updated = words_store.update_word(
        "user-1",
        created["word_id"],
        "試験",
        new_reading,
        "新メモ",
        moras_for(new_reading),
    )
    assert updated["word"] == "試験"
    assert updated["reading"] == new_reading
    assert updated["note"] == "新メモ"
    assert updated["created_at"] == created["created_at"]


def test_delete_word_removes_item(dynamodb_table):
    reading = "てすと"
    created = words_store.create_word(
        "user-1", "テスト", reading, "", moras_for(reading)
    )
    words_store.delete_word("user-1", created["word_id"])
    assert words_store.list_words("user-1") == []


def test_delete_word_missing_is_noop(dynamodb_table):
    words_store.delete_word("user-1", "missing-id")


def test_set_bookmark_updates_flag(dynamodb_table):
    reading = "てすと"
    created = words_store.create_word(
        "user-1", "テスト", reading, "", moras_for(reading)
    )
    updated = words_store.set_bookmark("user-1", created["word_id"], True)
    assert updated["bookmarked"] is True


def test_set_bookmark_not_found(dynamodb_table):
    with pytest.raises(words_store.NotFoundError):
        words_store.set_bookmark("user-1", "missing-id", True)


def test_list_words_only_returns_own_words(dynamodb_table):
    reading = "てすと"
    words_store.create_word("user-1", "テスト", reading, "", moras_for(reading))
    assert len(words_store.list_words("user-1")) == 1
    assert words_store.list_words("user-2") == []


class _ForcedPagingClient:
    """query() ごとに Limit=1 を強制し、複数ページに分割させるテスト用ラッパー。"""

    def __init__(self, client):
        self._client = client

    def query(self, **kwargs):
        kwargs.setdefault("Limit", 1)
        return self._client.query(**kwargs)

    def __getattr__(self, name):
        return getattr(self._client, name)


def test_list_words_paginates_across_multiple_pages(dynamodb_table, monkeypatch):
    real_client = words_store._client()
    for reading in ("いち", "にい", "さん"):
        words_store.create_word(
            "user-1", f"単語{reading}", reading, "", moras_for(reading)
        )

    monkeypatch.setattr(
        words_store, "_client", lambda: _ForcedPagingClient(real_client)
    )

    result = words_store.list_words("user-1")
    assert len(result) == 3
