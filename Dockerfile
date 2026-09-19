# ── Stage 1: 依存関係のエクスポート ──────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry poetry-plugin-export && \
    poetry export -f requirements.txt --output requirements.txt --without-hashes --only main

# ── Stage 2: 実行イメージ ─────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim

# Lambda Web Adapter（Lambda イベントを HTTP に変換する拡張機能）
# バージョンは https://github.com/awslabs/aws-lambda-web-adapter で確認
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app

# OS のセキュリティパッチを適用してからキャッシュを削除する
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 依存関係のインストール
COPY --from=builder /app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコピー
COPY app.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# Lambda Web Adapter の設定
# PORT: アプリが Listen するポート（LWA がリクエストを転送する先）
ENV PORT=8080
# LWA がアプリの起動完了を確認するヘルスチェックパス
ENV AWS_LWA_READINESS_CHECK_PATH=/

EXPOSE 8080

# workers=1, threads=8: Lambda の同時実行モデルに適した設定
# timeout=28: Lambda のタイムアウト（30 秒）より短く設定し、正常なシャットダウンを保証する
# worker-tmp-dir を省略することで、Lambda の書き込み可能領域 /tmp をデフォルトとして使用する
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "28", "app:app"]
