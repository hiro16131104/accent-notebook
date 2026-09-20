import hmac
import os
import secrets
from datetime import timedelta
from functools import wraps

import boto3
from flask import (
    Flask,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from werkzeug.middleware.proxy_fix import ProxyFix

from libs import words_store


def _load_config(param_env_var, literal_env_var, default=None):
    """設定値を取得する（SSM パラメータストア優先、なければ直値）。

    <param_env_var> に SSM パラメータ名が設定されていれば、実行時に
    SSM パラメータストアから値を取得する（local/dev/prod いずれも、
    SSM 経由で値を配る場合はこちらを使う。ローカルは AWS 認証情報が必要）。
    未設定なら <literal_env_var> の値をそのまま使う（未設定時は default）。
    """
    param_name = os.environ.get(param_env_var)
    if param_name:
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name=param_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    return os.environ.get(literal_env_var, default)


APP_ENV = os.environ.get("APP_ENV", "dev")
SECRET_KEY = _load_config(
    "SECRET_KEY_PARAM", "SECRET_KEY", "dev-only-insecure-secret-key"
)
GOOGLE_CLIENT_ID = _load_config("GOOGLE_CLIENT_ID_PARAM", "GOOGLE_CLIENT_ID", "")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # API Gateway/Lambda Web Adapter の手前は必ず HTTPS 終端のため、
    # dev（ローカル HTTP 起動）以外では Secure Cookie を強制する
    SESSION_COOKIE_SECURE=APP_ENV != "dev",
    # ログインセッションの有効期限。SESSION_REFRESH_EACH_REQUEST は
    # Flask のデフォルトで True のため、期限内にアクセスがあるたびに
    # Cookie の有効期限が自動延長される（スライディング方式）
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

# API Gateway → Lambda Web Adapter は X-Forwarded-Proto/Host を付与して転送してくる。
# これを信頼しないと url_for(_external=True) が http:// を返し、
# Google の認可済みリダイレクト URI（https）と不一致になる。
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


@app.before_request
def generate_csp_nonce():
    """自前のインラインスクリプト（Tailwind設定）用にリクエストごとのnonceを発行する。"""
    g.csp_nonce = secrets.token_urlsafe(16)


@app.after_request
def set_security_headers(response):
    """セキュリティ関連の HTTP レスポンスヘッダーを付与する。"""
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{g.csp_nonce}' https://cdn.tailwindcss.com "
        "https://accounts.google.com/gsi/client; "
        # style-src は Tailwind CDN がJITでスタイルを動的注入するため unsafe-inline が必要
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data: https://*.googleusercontent.com; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "frame-src https://accounts.google.com"
    )
    response.headers.pop("Server", None)
    # API Gateway/LWA の手前は必ず HTTPS 終端のため、dev（ローカル HTTP 起動）
    # 以外ではブラウザに恒久的な HTTPS 強制を指示する
    if APP_ENV != "dev":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    return response


@app.context_processor
def inject_env():
    return {
        "app_env": APP_ENV,
        "current_user": session.get("user"),
        "csp_nonce": g.csp_nonce,
    }


def login_required(view):
    """未ログイン時はログインページへリダイレクトする。"""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def _require_json():
    """Content-Type: application/json を強制する。

    ブラウザは application/json ボディを送る非単純リクエストに対して
    必ず CORS プリフライトを行うため、CORS を許可していない本APIでは
    他オリジンの <form> やスクリプトから直接叩くことができない
    （SameSite=Lax の Cookie 制御に加えたCSRF対策）。
    """
    if not request.is_json:
        abort(400, "Content-Type は application/json を指定してください。")


@app.route("/login")
def login():
    if "user" in session:
        return redirect(url_for("index"))
    return render_template("login.html", google_client_id=GOOGLE_CLIENT_ID)


@app.route("/auth/google/callback", methods=["POST"])
def auth_google_callback():
    """Google Identity Services が POST する ID トークンを検証してログインさせる。"""
    # GIS の login_uri 方式は g_csrf_token を Cookie とフォームの両方に載せるため、
    # 一致を確認することで CSRF を防ぐ（Google 公式ドキュメントの推奨実装）
    csrf_cookie = request.cookies.get("g_csrf_token")
    csrf_body = request.form.get("g_csrf_token")
    if (
        not csrf_cookie
        or not csrf_body
        or not hmac.compare_digest(csrf_cookie, csrf_body)
    ):
        abort(400, "CSRF トークンが一致しません。")

    credential = request.form.get("credential")
    if not credential:
        abort(400, "credential がありません。")

    try:
        # verify_oauth2_token の既定は clock_skew_in_seconds=0（許容誤差ゼロ）で、
        # サーバー・Googleの時刻がわずかにずれただけでも失敗しうるため、
        # 数秒の許容誤差を明示的に持たせる
        claims = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as error:
        # クライアントには詳細を返さず、原因調査用にサーバーログにのみ出力する
        app.logger.warning("Google ID トークンの検証に失敗しました: %s", error)
        abort(401, "Google ID トークンの検証に失敗しました。")

    session.clear()
    session.permanent = True
    session["user"] = {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "name": claims.get("name"),
        "picture": claims.get("picture"),
    }
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/words", methods=["GET"])
@login_required
def api_list_words():
    return jsonify(words_store.list_words(session["user"]["sub"]))


@app.route("/api/words", methods=["POST"])
@login_required
def api_create_word():
    _require_json()
    data = request.get_json()
    try:
        item = words_store.create_word(
            session["user"]["sub"],
            data.get("word"),
            data.get("reading"),
            data.get("note"),
            data.get("moras"),
            data.get("final_drop"),
        )
    except words_store.ValidationError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(item), 201


@app.route("/api/words/<word_id>", methods=["PUT"])
@login_required
def api_update_word(word_id):
    _require_json()
    data = request.get_json()
    try:
        item = words_store.update_word(
            session["user"]["sub"],
            word_id,
            data.get("word"),
            data.get("reading"),
            data.get("note"),
            data.get("moras"),
            data.get("final_drop"),
        )
    except words_store.NotFoundError:
        abort(404)
    except words_store.ValidationError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(item)


@app.route("/api/words/<word_id>", methods=["DELETE"])
@login_required
def api_delete_word(word_id):
    words_store.delete_word(session["user"]["sub"], word_id)
    return "", 204


@app.route("/api/words/<word_id>/bookmark", methods=["PATCH"])
@login_required
def api_set_bookmark(word_id):
    _require_json()
    data = request.get_json()
    try:
        item = words_store.set_bookmark(
            session["user"]["sub"], word_id, data.get("bookmarked")
        )
    except words_store.NotFoundError:
        abort(404)
    return jsonify(item)


if __name__ == "__main__":
    # python app.py での直接起動時のみ、GOOGLE_CLIENT_ID_PARAM を export
    # し忘れていても local 用パラメータを既定値として使う（export 済みなら
    # そちらを優先）。pytest やgunicorn からの import では実行されないため、
    # テスト実行時に意図せず SSM へ問い合わせることはない
    os.environ.setdefault(
        "GOOGLE_CLIENT_ID_PARAM", "/accent-notebook/local/envs/GOOGLE_CLIENT_ID"
    )
    os.environ.setdefault("WORDS_TABLE_NAME", "accent-notebook-words-local")
    GOOGLE_CLIENT_ID = _load_config("GOOGLE_CLIENT_ID_PARAM", "GOOGLE_CLIENT_ID", "")

    is_debug = APP_ENV == "dev"
    app.run(debug=is_debug, port=5050)
