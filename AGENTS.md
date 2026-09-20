# AGENTS.md — Accent Notebook

AI エージェント（Claude Code など）がこのリポジトリで作業する際のガイドです。

---

## プロジェクト概要

日本語アクセントを記録・学習するためのノートアプリ。  
Flask 3.x アプリを AWS Lambda（Lambda Web Adapter）上で動かす構成。

- **言語 / ランタイム**: Python 3.12
- **パッケージ管理**: Poetry
- **フロントエンド**: Tailwind CSS (CDN)、Jinja2 テンプレート、日本語 UI
- **インフラ**: AWS Lambda + API Gateway REST、Docker イメージで配信

---

## ディレクトリ構造

```
accent-notebook/
├── app.py                    # Flask アプリ本体・ルート定義
├── templates/
│   ├── base.html             # 全テンプレートの親 (Jinja2 継承)
│   └── index.html
├── static/                   # 静的ファイル
├── tests/
│   └── test_app.py
├── Dockerfile                 # マルチステージビルド (python:3.12-slim + LWA 0.9.1)
├── template.yaml              # AWS SAM テンプレート
├── samconfig.toml             # SAM デプロイ設定 (dev / prod)
├── deploy.sh                  # デプロイ / ローカル起動スクリプト
└── pyproject.toml            # Poetry 依存関係定義
```

---

## セキュリティ

`app.py` の `set_security_headers` で全レスポンスに付与:

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy`（Tailwind CDN・Google Fonts を許可）
- `Server` ヘッダーを削除（バージョン情報の秘匿）

---

## 環境変数

| 変数 | 値 | 説明 |
|------|----|------|
| `APP_ENV` | `dev` / `prod` | `dev` のとき Flask デバッグモード ON、UI に DEV バッジ表示 |
| `PORT` | `8080` | gunicorn / LWA がバインドするポート（Lambda 環境のみ） |
| `AWS_LWA_READINESS_CHECK_PATH` | `/` | LWA ヘルスチェックパス（Lambda 環境のみ） |

---

## インフラ・デプロイ

### Lambda 設定 (`template.yaml`)

- **アーキテクチャ**: arm64
- **メモリ**: 256 MB
- **タイムアウト**: 30 秒
- **ログ保持**: prod=90 日 / dev=14 日
- コールドスタート対策（定期ウォームアップ）は導入していない

### デプロイコマンド

```bash
# ローカル起動 (Docker, ポート 8080)
./deploy.sh local

# 開発環境デプロイ
./deploy.sh dev

# 本番環境デプロイ（確認プロンプトあり）
./deploy.sh prod

# テストをスキップしてデプロイ
./deploy.sh dev --skip-tests
```

`deploy.sh` は isort → black → flake8 → pytest を自動実行してからデプロイする。

### Dockerfile

- マルチステージビルド（`python:3.12-slim`）
- Lambda Web Adapter 0.9.1 を `/opt/extensions/lambda-adapter` にコピー
- gunicorn: `--workers 1 --threads 8 --timeout 28`

---

## ローカル開発

```bash
# 依存関係インストール
poetry install

# Flask 開発サーバー起動 (ポート 5050)
python app.py

# テスト
poetry run pytest

# フォーマット・lint
poetry run isort .
poetry run black .
poetry run flake8 .
```

---

## コーディング規約

- **コメントはすべて日本語**で記述する
- Black (line-length=88) / isort (profile=black) / flake8 に準拠
- `E203` は ignore、`.venv` は flake8 対象外
- 新しいテンプレートは必ず `templates/base.html` を継承する
- セキュリティ上の懸念（コマンドインジェクション・XSS・SQLi など）がある変更は行わない
