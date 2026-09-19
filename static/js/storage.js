const STORAGE_KEY = "accent-notebook:words";

/** localStorageから単語一覧を読み込む。不正・未設定時は空配列を返す。 */
export function loadWords() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.error("単語データの読み込みに失敗しました", error);
    return [];
  }
}

/** 単語一覧をlocalStorageに保存する。 */
export function saveWords(words) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(words));
  } catch (error) {
    console.error("単語データの保存に失敗しました", error);
  }
}
