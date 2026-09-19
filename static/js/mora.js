const KATAKANA_START = 0x30a1;
const KATAKANA_END = 0x30f6;
const KATAKANA_HIRAGANA_OFFSET = 0x60;
const SMALL_KANA = new Set(["ゃ", "ゅ", "ょ", "ぁ", "ぃ", "ぅ", "ぇ", "ぉ"]);
const HIRAGANA_PATTERN = /^[ぁ-ゖー]+$/;

/** カタカナをひらがなに変換する（長音符 ー はそのまま通す）。 */
export function toHiragana(input) {
  let result = "";
  for (const ch of input) {
    const code = ch.codePointAt(0);
    if (code >= KATAKANA_START && code <= KATAKANA_END) {
      result += String.fromCodePoint(code - KATAKANA_HIRAGANA_OFFSET);
    } else {
      result += ch;
    }
  }
  return result;
}

/** ひらがな（＋長音符）のみで構成されているかを判定する。 */
export function isHiraganaOnly(input) {
  return input.length > 0 && HIRAGANA_PATTERN.test(input);
}

/** 読み文字列をモーラ単位に分割する（拗音は直前の仮名と結合して1モーラ）。 */
export function splitIntoMoras(reading) {
  const chars = Array.from(reading);
  const moras = [];
  for (let i = 0; i < chars.length; i += 1) {
    const next = chars[i + 1];
    if (next && SMALL_KANA.has(next)) {
      moras.push(chars[i] + next);
      i += 1;
    } else {
      moras.push(chars[i]);
    }
  }
  return moras;
}
