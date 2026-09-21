import { toHiragana, splitIntoMoras } from "./mora.js";
import {
  loadWords,
  createWord,
  updateWord,
  deleteWord,
  setBookmark,
} from "./storage.js";

const state = {
  words: [],
  query: "",
  bookmarkedOnly: false,
  sortMode: "reading",
};

let draftMoras = [];
// 最後のモーラの直後で下がる（尾高）かどうか。最後のモーラが高のときのみ有効
let draftFinalDrop = false;
let editingId = null;
let pendingDeleteAction = null;
let deleting = false;
let saving = false;
const selectedIds = new Set();

const wordForm = document.getElementById("word-form");
const wordInput = document.getElementById("word-input");
const readingInput = document.getElementById("reading-input");
const noteInput = document.getElementById("note-input");
const formError = document.getElementById("form-error");
const moraEditor = document.getElementById("mora-editor");
const pitchPreview = document.getElementById("pitch-preview");
const searchInput = document.getElementById("search-input");
const bookmarkFilter = document.getElementById("bookmark-filter");
const sortModeSelect = document.getElementById("sort-mode");
const wordList = document.getElementById("word-list");
const emptyMessage = document.getElementById("empty-message");
const selectionToolbar = document.getElementById("selection-toolbar");
const selectAllCheckbox = document.getElementById("select-all");
const selectionCount = document.getElementById("selection-count");
const clearSelectionButton = document.getElementById("clear-selection");
const deleteSelectedButton = document.getElementById("delete-selected");
const addWordDialog = document.getElementById("add-word-dialog");
const addWordHeading = document.getElementById("add-word-heading");
const submitButton = document.getElementById("word-form-submit");
const openAddWordButton = document.getElementById("open-add-word");
const closeAddWordButton = document.getElementById("close-add-word");
const deleteConfirmDialog = document.getElementById("delete-confirm-dialog");
const deleteConfirmMessage = document.getElementById("delete-confirm-message");
const deleteConfirmError = document.getElementById("delete-confirm-error");
const deleteConfirmCancelButton = document.getElementById("delete-confirm-cancel");
const deleteConfirmOkButton = document.getElementById("delete-confirm-ok");

/** 属性・テキスト・子要素を指定してDOM要素を生成する小さなヘルパー。 */
function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.attrs) {
    for (const [key, value] of Object.entries(options.attrs)) {
      node.setAttribute(key, value);
    }
  }
  for (const child of children) {
    node.appendChild(child);
  }
  return node;
}

/** アクセント辞典記法（上罫線・核の強調）でモーラ列を描画する。
 *  下がり目（核）は「高の次が低」か、最後のモーラが高で finalDrop が真のときに付く。 */
function buildPitchNotation(moras, finalDrop = false) {
  const container = el("div", { className: "flex items-end gap-0.5" });
  moras.forEach((mora, index) => {
    const next = moras[index + 1];
    const isCore =
      mora.pitch === "H" && (next ? next.pitch === "L" : Boolean(finalDrop));
    let borderClass = "border-transparent";
    if (mora.pitch === "H") {
      // 下がり目（核）の直前は横棒も赤にして、下がるアクセント記号全体を赤で統一する
      borderClass = isCore ? "border-red-600" : "border-gray-800";
    }
    const classes = [
      "relative",
      "inline-flex",
      "items-center",
      "justify-center",
      "px-1",
      "text-sm",
      "leading-none",
      "pt-1",
      "border-t-2",
      borderClass,
    ];
    if (isCore) {
      classes.push("text-red-600", "font-bold");
    }
    const span = el("span", { className: classes.join(" "), text: mora.text });
    if (isCore) {
      // 下がり目を示す短い縦棒（幅は元の2/3程度、高さは全体の1/3程度）を右上に配置する
      span.appendChild(el("span", { className: "absolute right-0 top-0 w-[1.33px] h-2 bg-red-600" }));
    }
    container.appendChild(span);
  });
  return container;
}

function clearFormError() {
  formError.textContent = "";
  formError.classList.add("hidden");
}

function showFormError(message) {
  formError.textContent = message;
  formError.classList.remove("hidden");
}

/** 読みからモーラ配列を再計算する。既存の並びと一致するモーラは高低指定を保持する。
 *  保存時はサーバー側の分割結果が正となり、ここでの分割は入力中のプレビュー表示専用。 */
function regenerateDraftMoras(reading) {
  const texts = splitIntoMoras(reading);
  const previous = draftMoras;
  draftMoras = texts.map((text, i) => ({
    text,
    pitch: previous[i] && previous[i].text === text ? previous[i].pitch : "L",
  }));
  // 最後のモーラが変わった場合は、尾高の指定を引き継がない
  const last = draftMoras.length - 1;
  const lastUnchanged =
    last >= 0 && previous.length === draftMoras.length && previous[last].text === draftMoras[last].text;
  if (!lastUnchanged || draftMoras[last].pitch !== "H") {
    draftFinalDrop = false;
  }
}

/** モーラの表示状態を返す。最後のモーラのみ「高（直後で下がる）」を持つ。 */
function moraState(index) {
  if (draftMoras[index].pitch !== "H") return "low";
  const isLast = index === draftMoras.length - 1;
  return isLast && draftFinalDrop ? "drop" : "high";
}

/** モーラを押したときの状態遷移。最後のモーラは 低→高→高（直後で下がる）→低 の3状態。 */
function toggleMora(index) {
  const isLast = index === draftMoras.length - 1;
  const state = moraState(index);
  if (state === "low") {
    draftMoras[index].pitch = "H";
  } else if (state === "high" && isLast) {
    draftFinalDrop = true;
  } else {
    draftMoras[index].pitch = "L";
    if (isLast) draftFinalDrop = false;
  }
}

const MORA_STATE_LABELS = {
  low: "低",
  high: "高",
  drop: "高（直後で下がる）",
};

function renderMoraEditor() {
  moraEditor.innerHTML = "";
  if (draftMoras.length === 0) {
    moraEditor.appendChild(
      el("p", {
        className: "text-xs text-gray-400",
        text: "読みを入力すると拍が表示されます。",
      }),
    );
    return;
  }
  draftMoras.forEach((mora, index) => {
    const state = moraState(index);
    const isHigh = state !== "low";
    let stateClass = "bg-white text-gray-700 border-gray-300";
    if (state === "high") stateClass = "bg-gray-900 text-white border-gray-900";
    if (state === "drop") stateClass = "bg-gray-900 text-white border-red-600 ring-2 ring-red-600";
    const button = el(
      "button",
      {
        // スマホで押しやすいよう最小サイズを確保し、連続タップでの拡大表示を防ぐ
        className: `min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 touch-manipulation px-2 py-1 rounded-lg text-sm font-semibold border transition-colors ${stateClass}`,
        text: mora.text,
        attrs: {
          type: "button",
          "aria-pressed": String(isHigh),
          "aria-label": `${mora.text} を ${MORA_STATE_LABELS[state]} に設定中。押すと切替`,
        },
      },
      state === "drop" ? [el("span", { className: "ml-0.5 text-xs text-red-400", text: "↓" })] : [],
    );
    button.addEventListener("click", () => {
      toggleMora(index);
      renderMoraEditor();
      renderPitchPreview();
    });
    moraEditor.appendChild(button);
  });
}

function renderPitchPreview() {
  pitchPreview.innerHTML = "";
  if (draftMoras.length === 0) return;
  pitchPreview.appendChild(buildPitchNotation(draftMoras, draftFinalDrop));
}

function matchesFilters(word) {
  const query = state.query.trim();
  const matchesQuery =
    query === "" || word.word.includes(query) || word.reading.includes(query);
  const matchesBookmark = !state.bookmarkedOnly || word.bookmarked;
  return matchesQuery && matchesBookmark;
}

function replaceWordInState(updated) {
  const index = state.words.findIndex((w) => w.word_id === updated.word_id);
  if (index !== -1) state.words[index] = updated;
}

function buildWordCard(word) {
  const card = el("li", {
    className:
      "bg-white rounded-xl border border-gray-200 shadow-sm p-3 flex items-start gap-3 hover:border-gray-300 transition-colors",
  });

  const checkbox = el("input", {
    className: "mt-1 h-4 w-4 rounded border-gray-300 accent-indigo-600 shrink-0",
    attrs: { type: "checkbox", "aria-label": `${word.word} を選択` },
  });
  checkbox.checked = selectedIds.has(word.word_id);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      selectedIds.add(word.word_id);
    } else {
      selectedIds.delete(word.word_id);
    }
    render();
  });
  card.appendChild(checkbox);

  const left = el("div", { className: "min-w-0" });
  const headerRow = el("div", { className: "flex items-baseline gap-2 flex-wrap" });
  headerRow.appendChild(el("span", { className: "font-bold", text: word.word }));
  headerRow.appendChild(el("span", { className: "text-xs text-gray-400", text: word.reading }));
  left.appendChild(headerRow);
  left.appendChild(buildPitchNotation(word.moras, word.final_drop));
  if (word.note) {
    left.appendChild(
      el("p", {
        className: "text-xs text-gray-500 mt-1 whitespace-pre-wrap",
        text: word.note,
      }),
    );
  }

  const actions = el("div", { className: "flex items-center gap-1 shrink-0 ml-auto" });

  const bookmarkButton = el("button", {
    className: "text-lg leading-none px-1",
    text: word.bookmarked ? "★" : "☆",
    attrs: {
      type: "button",
      "aria-pressed": String(word.bookmarked),
      "aria-label": word.bookmarked ? "ブックマークを解除" : "ブックマークに追加",
    },
  });
  bookmarkButton.addEventListener("click", async () => {
    try {
      const updated = await setBookmark(word.word_id, !word.bookmarked);
      replaceWordInState(updated);
      render();
    } catch (error) {
      window.alert(error.message);
    }
  });

  const editButton = el("button", {
    className: "text-xs text-gray-400 hover:text-indigo-600 px-1",
    text: "編集",
    attrs: { type: "button", "aria-label": `${word.word} を編集` },
  });
  editButton.addEventListener("click", () => openDialogForEdit(word));

  const deleteButton = el("button", {
    className: "text-xs text-gray-400 hover:text-red-600 px-1",
    text: "削除",
    attrs: { type: "button", "aria-label": `${word.word} を削除` },
  });
  deleteButton.addEventListener("click", () => {
    openDeleteConfirm(`「${word.word}」を削除しますか？`, async () => {
      await deleteWord(word.word_id);
      state.words = state.words.filter((w) => w.word_id !== word.word_id);
      render();
    });
  });

  actions.appendChild(bookmarkButton);
  actions.appendChild(editButton);
  actions.appendChild(deleteButton);

  card.appendChild(left);
  card.appendChild(actions);
  return card;
}

function renderSelectionToolbar(filtered) {
  for (const id of Array.from(selectedIds)) {
    if (!state.words.some((w) => w.word_id === id)) selectedIds.delete(id);
  }

  if (filtered.length === 0) {
    selectionToolbar.classList.add("hidden");
    return;
  }
  selectionToolbar.classList.remove("hidden");

  const count = selectedIds.size;
  selectionCount.textContent = count > 0 ? `${count}件選択中` : "";
  deleteSelectedButton.disabled = count === 0;
  clearSelectionButton.disabled = count === 0;

  const allSelected = filtered.every((w) => selectedIds.has(w.word_id));
  selectAllCheckbox.checked = allSelected;
  selectAllCheckbox.indeterminate = count > 0 && !allSelected;
}

function render() {
  const filtered = state.words.filter(matchesFilters);
  if (state.sortMode === "createdAt") {
    filtered.sort((a, b) => a.created_at.localeCompare(b.created_at));
  } else {
    filtered.sort((a, b) => a.reading.localeCompare(b.reading, "ja"));
  }

  wordList.innerHTML = "";
  if (filtered.length === 0) {
    emptyMessage.classList.remove("hidden");
  } else {
    emptyMessage.classList.add("hidden");
    filtered.forEach((word) => wordList.appendChild(buildWordCard(word)));
  }
  renderSelectionToolbar(filtered);
}

function resetForm() {
  wordForm.reset();
  draftMoras = [];
  draftFinalDrop = false;
  renderMoraEditor();
  renderPitchPreview();
  clearFormError();
}

function openDialogForAdd() {
  editingId = null;
  addWordHeading.textContent = "単語を追加";
  submitButton.textContent = "追加";
  clearFormError();
  addWordDialog.showModal();
  wordInput.focus();
}

function openDialogForEdit(word) {
  editingId = word.word_id;
  addWordHeading.textContent = "単語を編集";
  submitButton.textContent = "保存";
  clearFormError();
  wordInput.value = word.word;
  readingInput.value = word.reading;
  noteInput.value = word.note || "";
  draftMoras = word.moras.map((m) => ({ ...m }));
  draftFinalDrop = Boolean(word.final_drop);
  renderMoraEditor();
  renderPitchPreview();
  addWordDialog.showModal();
  wordInput.focus();
}

/** 追加・保存中はボタンのラベルを切り替え、無効化して二重送信とダイアログの誤クローズを防ぐ。 */
function setSaving(value) {
  saving = value;
  submitButton.disabled = value;
  closeAddWordButton.disabled = value;
  submitButton.setAttribute("aria-busy", String(value));
  const idleLabel = editingId ? "保存" : "追加";
  submitButton.textContent = value ? `${idleLabel}中…` : idleLabel;
}

/** 削除中は確認ダイアログを開いたまま、ボタンを無効化して二重操作を防ぐ。 */
function setDeleting(value) {
  deleting = value;
  deleteConfirmOkButton.disabled = value;
  deleteConfirmCancelButton.disabled = value;
  deleteConfirmOkButton.textContent = value ? "削除中…" : "削除";
}

function clearDeleteError() {
  deleteConfirmError.textContent = "";
  deleteConfirmError.classList.add("hidden");
}

function showDeleteError(message) {
  deleteConfirmError.textContent = message;
  deleteConfirmError.classList.remove("hidden");
}

/** 削除確認ダイアログを開く。onConfirm は削除処理で、失敗時は例外を投げるとダイアログ内に表示する。 */
function openDeleteConfirm(message, onConfirm) {
  pendingDeleteAction = onConfirm;
  deleteConfirmMessage.textContent = message;
  clearDeleteError();
  setDeleting(false);
  deleteConfirmDialog.showModal();
}

function bulkDeleteMessage(count) {
  return `選択した${count}件の単語を削除しますか？`;
}

deleteConfirmOkButton.addEventListener("click", async () => {
  const action = pendingDeleteAction;
  if (!action || deleting) return;
  clearDeleteError();
  setDeleting(true);
  try {
    await action();
    deleteConfirmDialog.close();
  } catch (error) {
    if (deleteConfirmDialog.open) {
      showDeleteError(error.message);
    } else {
      window.alert(error.message);
    }
  } finally {
    setDeleting(false);
  }
});
deleteConfirmCancelButton.addEventListener("click", () => deleteConfirmDialog.close());
// 削除中は Esc・背景クリックでも閉じないようにする
deleteConfirmDialog.addEventListener("cancel", (event) => {
  if (deleting) event.preventDefault();
});
deleteConfirmDialog.addEventListener("click", (event) => {
  if (event.target === deleteConfirmDialog && !deleting) {
    deleteConfirmDialog.close();
  }
});
deleteConfirmDialog.addEventListener("close", () => {
  pendingDeleteAction = null;
  clearDeleteError();
});

openAddWordButton.addEventListener("click", openDialogForAdd);
closeAddWordButton.addEventListener("click", () => addWordDialog.close());
addWordDialog.addEventListener("click", (event) => {
  if (event.target === addWordDialog && !saving) {
    addWordDialog.close();
  }
});
// 追加・保存中は Esc でも閉じないようにする
addWordDialog.addEventListener("cancel", (event) => {
  if (saving) event.preventDefault();
});
addWordDialog.addEventListener("close", () => {
  resetForm();
  editingId = null;
});

readingInput.addEventListener("input", () => {
  const hira = toHiragana(readingInput.value);
  if (hira !== readingInput.value) {
    readingInput.value = hira;
  }
  regenerateDraftMoras(hira);
  renderMoraEditor();
  renderPitchPreview();
  clearFormError();
});

wordInput.addEventListener("input", clearFormError);

wordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (saving) return;

  const word = wordInput.value.trim();
  const reading = readingInput.value.trim();
  const note = noteInput.value.trim();

  if (!word || !reading || draftMoras.length === 0) {
    showFormError("表記と読みは必須です。");
    return;
  }

  const payload = {
    word,
    reading,
    note,
    moras: draftMoras.map((m) => ({ ...m })),
    final_drop: draftFinalDrop,
  };
  clearFormError();
  setSaving(true);
  try {
    if (editingId) {
      const updated = await updateWord(editingId, payload);
      replaceWordInState(updated);
    } else {
      const created = await createWord(payload);
      state.words.push(created);
    }
    addWordDialog.close();
    render();
  } catch (error) {
    showFormError(error.message);
  } finally {
    setSaving(false);
  }
});

searchInput.addEventListener("input", () => {
  state.query = searchInput.value;
  render();
});

bookmarkFilter.addEventListener("change", () => {
  state.bookmarkedOnly = bookmarkFilter.checked;
  render();
});

sortModeSelect.addEventListener("change", () => {
  state.sortMode = sortModeSelect.value;
  render();
});

selectAllCheckbox.addEventListener("change", () => {
  const filtered = state.words.filter(matchesFilters);
  if (selectAllCheckbox.checked) {
    filtered.forEach((w) => selectedIds.add(w.word_id));
  } else {
    filtered.forEach((w) => selectedIds.delete(w.word_id));
  }
  render();
});

clearSelectionButton.addEventListener("click", () => {
  selectedIds.clear();
  render();
});

deleteSelectedButton.addEventListener("click", () => {
  const count = selectedIds.size;
  if (count === 0) return;
  openDeleteConfirm(bulkDeleteMessage(count), async () => {
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => deleteWord(id)));
    const failedCount = results.filter((r) => r.status === "rejected").length;
    // 一括削除は部分失敗し得るため、サーバーの状態を取得し直して同期する
    state.words = await loadWords();
    // 削除できた単語の選択は render 内で外れ、失敗した単語だけ選択が残る
    render();
    if (failedCount > 0) {
      // 失敗分だけを対象に、ダイアログを開いたまま再試行できるようにする
      deleteConfirmMessage.textContent = bulkDeleteMessage(selectedIds.size);
      throw new Error(`${failedCount}件の削除に失敗しました。もう一度削除するか、キャンセルしてください。`);
    }
  });
});

async function init() {
  try {
    state.words = await loadWords();
  } catch (error) {
    window.alert(error.message);
  }
  renderMoraEditor();
  renderPitchPreview();
  render();
}

init();
