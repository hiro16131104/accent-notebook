import os

from flask import Flask, render_template

app = Flask(__name__)


@app.after_request
def set_security_headers(response):
    """セキュリティ関連の HTTP レスポンスヘッダーを付与する。"""
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    response.headers.pop("Server", None)
    return response


@app.context_processor
def inject_env():
    return {"app_env": os.environ.get("APP_ENV", "dev")}


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=os.environ.get("APP_ENV", "dev") == "dev", port=5050)
