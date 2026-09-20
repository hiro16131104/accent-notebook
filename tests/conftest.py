import boto3
import pytest
from moto import mock_aws

from libs.mora import split_into_moras

WORDS_TABLE_NAME = "accent-notebook-words-test"


def moras_for(reading, pitch="L"):
    """指定した読みに対して、全モーラを同じ高低に設定した配列を作る（テスト用）。"""
    return [{"text": text, "pitch": pitch} for text in split_into_moras(reading)]


@pytest.fixture
def dynamodb_table(monkeypatch):
    """moto でDynamoDBをモックし、単語テーブルを用意する。"""
    monkeypatch.setenv("WORDS_TABLE_NAME", WORDS_TABLE_NAME)
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=WORDS_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "word_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "word_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@pytest.fixture
def client():
    """Flask テストクライアントを生成する。"""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    """ログイン済みセッションを持つテストクライアントを生成する。"""
    with client.session_transaction() as sess:
        sess["user"] = {
            "sub": "user-1",
            "email": "user@example.com",
            "name": "Test User",
        }
    return client
