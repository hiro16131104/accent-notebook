"""アプリケーションログの設定。

Lambda 上では標準エラー出力のログが CloudWatch Logs に自動で送られるため、
ファイル出力はせず、人が読みやすいテキスト形式で標準エラー出力へ出す。
"""

import logging

from flask import g, has_request_context

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(message)s"


class RequestIdFilter(logging.Filter):
    """ログにリクエストIDを付与する（リクエスト外のログは "-"）。"""

    def filter(self, record):
        record.request_id = (
            getattr(g, "request_id", "-") if has_request_context() else "-"
        )
        return True


def setup_logging(app, debug):
    """app.logger のハンドラー・書式・ログレベルを設定する。"""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    # Flask 既定のハンドラーを置き換える（二重出力を防ぐ）
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG if debug else logging.INFO)
    # python app.py 起動時の werkzeug 標準アクセスログは、
    # 自前のリクエストログと重複するため WARNING 以上に絞る
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
