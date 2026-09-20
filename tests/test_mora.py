from libs.mora import is_hiragana_only, split_into_moras


def test_is_hiragana_only_accepts_hiragana_and_long_vowel_mark():
    assert is_hiragana_only("てすとー")


def test_is_hiragana_only_rejects_katakana():
    assert not is_hiragana_only("テスト")


def test_is_hiragana_only_rejects_empty_string():
    assert not is_hiragana_only("")


def test_split_into_moras_combines_small_kana_with_preceding_char():
    assert split_into_moras("きょう") == ["きょ", "う"]


def test_split_into_moras_treats_leading_small_kana_as_its_own_mora():
    # 直前の仮名が無い場合、拗音単体でも1モーラとして扱う
    assert split_into_moras("ゃ") == ["ゃ"]


def test_split_into_moras_plain_reading():
    assert split_into_moras("てすと") == ["て", "す", "と"]


def test_split_into_moras_empty_reading_returns_empty_list():
    assert split_into_moras("") == []
