/** レスポンスがエラーの場合、サーバーが返したメッセージを取り出す。 */
async function extractErrorMessage(res) {
  try {
    const data = await res.json();
    if (data && data.error) return data.error;
  } catch (error) {
    // JSON以外のレスポンスは無視してデフォルトメッセージを使う
  }
  return "通信に失敗しました。";
}

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(await extractErrorMessage(res));
  }
  if (res.status === 204) return null;
  return res.json();
}

/** ログインユーザーの単語一覧をサーバーから取得する。 */
export function loadWords() {
  return request("/api/words");
}

/** 単語を新規登録する。 */
export function createWord(payload) {
  return request("/api/words", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 単語を更新する。 */
export function updateWord(wordId, payload) {
  return request(`/api/words/${encodeURIComponent(wordId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

/** 単語を削除する。 */
export function deleteWord(wordId) {
  return request(`/api/words/${encodeURIComponent(wordId)}`, {
    method: "DELETE",
  });
}

/** ブックマーク状態を更新する。 */
export function setBookmark(wordId, bookmarked) {
  return request(`/api/words/${encodeURIComponent(wordId)}/bookmark`, {
    method: "PATCH",
    body: JSON.stringify({ bookmarked }),
  });
}
