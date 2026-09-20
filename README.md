# Accent Notebook

日本語アクセントを記録・学習するためのノートアプリ。

## 技術スタック

| 項目 | 内容 |
|------|------|
| 言語 | Python 3.12 |
| フレームワーク | Flask 3.x |
| フロントエンド | Tailwind CSS (CDN), Jinja2 |
| 認証 | Google Identity Services（Google OAuth ログイン） |
| データストア | DynamoDB |
| パッケージ管理 | Poetry |
| インフラ | AWS Lambda + API Gateway (Lambda Web Adapter) |
| コンテナ | Docker (multi-stage build) |
| IaC | AWS SAM |

## ローカル開発

### 前提条件
- Python 3.12+
- Poetry
- Docker（コンテナ起動・デプロイ時のみ）

### セットアップ

```bash
# 依存関係のインストール
poetry install

# 開発サーバー起動 (Flask built-in)
python app.py
```

http://localhost:5050 で確認できます。

Google ログインおよび単語データの読み書きには、SSM パラメータストア（`GOOGLE_CLIENT_ID` など）と
DynamoDB（`accent-notebook-words-local` テーブル）へのアクセス権を持つ AWS 認証情報が必要です。
詳細は [AGENTS.md](AGENTS.md) の環境変数の項を参照してください。

### Docker でローカル起動

```bash
./deploy.sh local
```

`http://localhost:8080` で確認できます。

## テスト

```bash
poetry run pytest
```

## デプロイ

### 前提条件
- AWS CLI（設定済み）
- AWS SAM CLI
- Docker

### コマンド

```bash
# 開発環境へデプロイ
./deploy.sh dev

# 本番環境へデプロイ
./deploy.sh prod

# テストをスキップしてデプロイ
./deploy.sh dev --skip-tests
```

デプロイ前に自動でコードのフォーマット（isort / black）とリント（flake8）、テストが実行されます。

## プロジェクト構成

```
accent-notebook/
├── app.py                  # Flask アプリ・ルーティング・Google認証
├── libs/
│   ├── mora.py              # モーラ分割・ひらがな判定ロジック
│   └── words_store.py       # DynamoDB アクセス・単語のバリデーション
├── templates/
│   ├── base.html           # 共通レイアウト
│   ├── index.html          # トップページ
│   └── login.html          # ログインページ
├── static/                 # 静的ファイル
├── tests/
│   ├── conftest.py          # 共通フィクスチャ（DynamoDBモック等）
│   ├── test_app.py
│   ├── test_words_store.py
│   └── test_mora.py
├── Dockerfile               # マルチステージビルド
├── template.yaml             # AWS SAM テンプレート
├── samconfig.toml            # SAM デプロイ設定 (dev / prod)
├── deploy.sh                 # デプロイ / ローカル起動スクリプト
└── pyproject.toml            # Poetry 依存関係定義
```

## コードスタイル

[Black](https://github.com/psf/black)・[isort](https://pycqa.github.io/isort/)・[Flake8](https://flake8.pycqa.org/) を使用しています。設定は `pyproject.toml` にまとめています。

```bash
# フォーマット
poetry run isort .
poetry run black .

# リント
poetry run flake8 .
```

## ライセンス

[MIT](LICENSE)
