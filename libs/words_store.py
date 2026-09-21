"""単語データのDynamoDBアクセスとバリデーション。"""

import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from libs.mora import is_hiragana_only, split_into_moras

JST = ZoneInfo("Asia/Tokyo")

MAX_WORD_LENGTH = 100
MAX_READING_LENGTH = 100
MAX_NOTE_LENGTH = 1000

# boto3 の resource API（Table など）は2024年11月にメンテナンスモード入りし、
# 新機能は client 側にのみ追加される方針のため、低レベル client を使う。
# その代わり Python のネイティブ型 <-> DynamoDB型 の変換を自前で行う必要がある。
_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


class ValidationError(Exception):
    """入力値が不正な場合に送出する。"""


class NotFoundError(Exception):
    """対象の単語が存在しない場合に送出する。"""


def _client():
    return boto3.client("dynamodb")


def _table_name():
    return os.environ.get("WORDS_TABLE_NAME", "accent-notebook-words-local")


def _serialize_item(item):
    return {key: _serializer.serialize(value) for key, value in item.items()}


def _deserialize_item(item):
    return {key: _deserializer.deserialize(value) for key, value in item.items()}


def list_words(user_id):
    """ログインユーザーの単語を全件取得する。

    DynamoDB の Query は1回のレスポンスが最大1MBまでのため、
    LastEvaluatedKey が返る限りページングして全件取得する。
    """
    client = _client()
    items = []
    query_kwargs = {
        "TableName": _table_name(),
        "KeyConditionExpression": "user_id = :user_id",
        "ExpressionAttributeValues": {":user_id": _serializer.serialize(user_id)},
    }
    while True:
        resp = client.query(**query_kwargs)
        items.extend(_deserialize_item(item) for item in resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return items
        query_kwargs["ExclusiveStartKey"] = last_key


def get_word(user_id, word_id):
    """単語を1件取得する。存在しない場合は None を返す。"""
    resp = _client().get_item(
        TableName=_table_name(),
        Key=_serialize_item({"user_id": user_id, "word_id": word_id}),
    )
    item = resp.get("Item")
    return _deserialize_item(item) if item else None


def _validate_word_reading(user_id, word, reading, exclude_word_id=None):
    word = (word or "").strip()
    reading = (reading or "").strip()
    if not word or not reading:
        raise ValidationError("表記と読みは必須です。")
    if len(word) > MAX_WORD_LENGTH:
        raise ValidationError(f"表記は{MAX_WORD_LENGTH}文字以内で入力してください。")
    if len(reading) > MAX_READING_LENGTH:
        raise ValidationError(f"読みは{MAX_READING_LENGTH}文字以内で入力してください。")
    if not is_hiragana_only(reading):
        raise ValidationError("読みはひらがなで入力してください。")
    for item in list_words(user_id):
        if item["word_id"] == exclude_word_id:
            continue
        if item["word"] == word and item["reading"] == reading:
            raise ValidationError("同じ表記・読みの単語が既に登録されています。")
    return word, reading


def _validate_moras(reading, moras):
    # モーラ分割はバックエンドの split_into_moras を正とし、
    # フロントエンドから送られてきたテキストとの一致を確認する
    expected_texts = split_into_moras(reading)
    if not expected_texts:
        raise ValidationError("読みを入力してください。")
    if not isinstance(moras, list) or len(moras) != len(expected_texts):
        raise ValidationError("拍の指定が不正です。")
    validated = []
    for expected_text, mora in zip(expected_texts, moras):
        if not isinstance(mora, dict) or mora.get("text") != expected_text:
            raise ValidationError("拍の指定が不正です。")
        pitch = mora.get("pitch")
        if pitch not in ("H", "L"):
            raise ValidationError("拍の指定が不正です。")
        validated.append({"text": expected_text, "pitch": pitch})
    return validated


def _validate_final_drop(final_drop, moras):
    """最後のモーラの直後で下がる（尾高）かどうかのフラグを検証する。

    未指定は False として扱う（フラグ導入前の既存データとの互換）。
    最後のモーラが低のときは下がり目を置けないため False に丸める。
    """
    if final_drop is None:
        return False
    if not isinstance(final_drop, bool):
        raise ValidationError("下がり目の指定が不正です。")
    return final_drop and moras[-1]["pitch"] == "H"


def _validate_note(note):
    note = (note or "").strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise ValidationError(f"メモは{MAX_NOTE_LENGTH}文字以内で入力してください。")
    return note


def create_word(user_id, word, reading, note, moras, final_drop=None):
    """単語を新規登録する。"""
    word, reading = _validate_word_reading(user_id, word, reading)
    validated_moras = _validate_moras(reading, moras)
    validated_final_drop = _validate_final_drop(final_drop, validated_moras)
    note = _validate_note(note)
    now = datetime.now(JST).isoformat()
    item = {
        "user_id": user_id,
        "word_id": str(uuid.uuid4()),
        "word": word,
        "reading": reading,
        "moras": validated_moras,
        "final_drop": validated_final_drop,
        "note": note,
        "bookmarked": False,
        "created_at": now,
        "updated_at": now,
    }
    _client().put_item(TableName=_table_name(), Item=_serialize_item(item))
    return item


def update_word(user_id, word_id, word, reading, note, moras, final_drop=None):
    """単語を更新する。"""
    existing = get_word(user_id, word_id)
    if existing is None:
        raise NotFoundError()
    word, reading = _validate_word_reading(
        user_id, word, reading, exclude_word_id=word_id
    )
    validated_moras = _validate_moras(reading, moras)
    validated_final_drop = _validate_final_drop(final_drop, validated_moras)
    note = _validate_note(note)
    item = {
        **existing,
        "word": word,
        "reading": reading,
        "moras": validated_moras,
        "final_drop": validated_final_drop,
        "note": note,
        "updated_at": datetime.now(JST).isoformat(),
    }
    _client().put_item(TableName=_table_name(), Item=_serialize_item(item))
    return item


def delete_word(user_id, word_id):
    """単語を削除する（存在しなくてもエラーにしない）。"""
    _client().delete_item(
        TableName=_table_name(),
        Key=_serialize_item({"user_id": user_id, "word_id": word_id}),
    )


def set_bookmark(user_id, word_id, bookmarked):
    """ブックマーク状態を更新する。"""
    existing = get_word(user_id, word_id)
    if existing is None:
        raise NotFoundError()
    _client().update_item(
        TableName=_table_name(),
        Key=_serialize_item({"user_id": user_id, "word_id": word_id}),
        UpdateExpression="SET bookmarked = :b",
        ExpressionAttributeValues={":b": _serializer.serialize(bool(bookmarked))},
    )
    existing["bookmarked"] = bool(bookmarked)
    return existing
