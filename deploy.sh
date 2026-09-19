#!/usr/bin/env bash
# ==============================================================
# Accent Notebook デプロイ / ローカル起動スクリプト
#
# Usage:
#   ./deploy.sh local        # Docker でローカル起動（ポート 8080）
#   ./deploy.sh dev          # 開発環境へデプロイ
#   ./deploy.sh prod         # 本番環境へデプロイ
#
# 前提条件:
#   - Docker が起動済み
#   - AWS CLI がインストール・設定済み（dev/prod のみ）
#   - SAM CLI がインストール済み（dev/prod のみ）
# ==============================================================

set -euo pipefail

# ── 引数チェック ────────────────────────────────────────────────
ENV="${1:-}"
SKIP_TESTS=false

# オプション解析（--skip-tests）
for arg in "$@"; do
    if [[ "$arg" == "--skip-tests" ]]; then
        SKIP_TESTS=true
    fi
done

if [[ "$ENV" != "local" && "$ENV" != "dev" && "$ENV" != "prod" ]]; then
    echo "Error: 環境を指定してください。"
    echo ""
    echo "Usage: $0 <local|dev|prod> [--skip-tests]"
    echo "  例:  $0 local"
    echo "  例:  $0 dev"
    echo "  例:  $0 dev --skip-tests"
    echo "  例:  $0 prod"
    exit 1
fi

# ── コードフォーマット ───────────────────────────────────────────
echo "======================================================"
echo "  コードフォーマット"
echo "======================================================"
echo ""
echo "[0/2] isort & black を実行..."
poetry run isort .
poetry run black .
echo "      OK"
echo ""
echo "[0/2] flake8 を実行..."
poetry run flake8 .
echo "      OK"
echo ""
if [[ "$SKIP_TESTS" == "true" ]]; then
    echo "[0/2] pytest をスキップ（--skip-tests）"
else
    echo "[0/2] pytest を実行..."
    poetry run pytest
    echo "      OK"
fi
echo ""

# ── ローカル起動 ─────────────────────────────────────────────────
if [[ "$ENV" == "local" ]]; then
    IMAGE_NAME="accent-notebook-local"
    PORT=8080

    echo "======================================================"
    echo "  ローカル起動モード"
    echo "  イメージ名 : ${IMAGE_NAME}"
    echo "  URL        : http://localhost:${PORT}"
    echo "======================================================"
    echo ""
    echo "[1/2] Docker イメージをビルド..."
    docker build -t "${IMAGE_NAME}" .

    echo ""
    echo "[2/2] コンテナを起動..."
    echo "      停止するには Ctrl+C を押してください。"
    echo ""
    # --rm: 停止時にコンテナを自動削除
    docker run --rm -p "${PORT}:${PORT}" "${IMAGE_NAME}"
    exit 0
fi

# ── 設定（dev / prod 共通）──────────────────────────────────────
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
STACK_NAME="accent-notebook-${ENV}"
ECR_REPO_NAME="accent-notebook-${ENV}"

# AWS アカウント ID を取得
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"

# ── ヘッダー表示 ────────────────────────────────────────────────
echo "======================================================"
echo "  デプロイ先  : ${ENV}"
echo "  スタック名  : ${STACK_NAME}"
echo "  リージョン  : ${REGION}"
echo "  ECR URI     : ${ECR_URI}"
echo "======================================================"

# ── 本番環境の確認プロンプト ────────────────────────────────────
if [[ "$ENV" == "prod" ]]; then
    echo ""
    echo "警告: 本番環境へのデプロイです。"
    read -rp "続行しますか？ (yes/N): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "デプロイをキャンセルしました。"
        exit 0
    fi
fi

# ── Step 1: ECR リポジトリの確認・作成 ──────────────────────────
echo ""
echo "[1/4] ECR リポジトリの確認・作成..."

aws ecr describe-repositories \
    --repository-names "${ECR_REPO_NAME}" \
    --region "${REGION}" \
    --output text > /dev/null 2>&1 \
|| \
aws ecr create-repository \
    --repository-name "${ECR_REPO_NAME}" \
    --region "${REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --output text > /dev/null

echo "      OK: ${ECR_REPO_NAME}"

# ── Step 2: ECR へログイン ───────────────────────────────────────
echo ""
echo "[2/4] ECR へログイン..."

aws ecr get-login-password --region "${REGION}" | \
    docker login \
        --username AWS \
        --password-stdin \
        "${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# ── Step 3: SAM ビルド（Docker イメージのビルド）────────────────
echo ""
echo "[3/4] SAM ビルド..."

sam build

# ── Step 4: SAM デプロイ ────────────────────────────────────────
echo ""
echo "[4/4] SAM デプロイ (${ENV})..."
# prod は samconfig.toml の confirm_changeset=true によりチェンジセット確認あり

sam deploy \
    --config-env "${ENV}" \
    --image-repositories "AccentNotebookFunction=${ECR_URI}" \
    --no-fail-on-empty-changeset

# ── 完了メッセージ ───────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  デプロイ完了: ${STACK_NAME}"

# API エンドポイントを出力
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text 2>/dev/null || echo "(取得できませんでした)")

echo "  API URL: ${API_URL}"
echo "======================================================"
