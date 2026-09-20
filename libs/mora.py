"""読み仮名のひらがな判定・モーラ分割ロジック（static/js/mora.js のPython版）。"""

import re

SMALL_KANA = {"ゃ", "ゅ", "ょ", "ぁ", "ぃ", "ぅ", "ぇ", "ぉ"}
HIRAGANA_PATTERN = re.compile(r"^[ぁ-ゖー]+$")


def is_hiragana_only(text):
    """ひらがな（＋長音符）のみで構成されているかを判定する。"""
    return bool(text) and bool(HIRAGANA_PATTERN.match(text))


def split_into_moras(reading):
    """読み文字列をモーラ単位に分割する（拗音は直前の仮名と結合して1モーラ）。"""
    chars = list(reading)
    moras = []
    i = 0
    while i < len(chars):
        next_char = chars[i + 1] if i + 1 < len(chars) else None
        if next_char and next_char in SMALL_KANA:
            moras.append(chars[i] + next_char)
            i += 2
        else:
            moras.append(chars[i])
            i += 1
    return moras
