import { toHiragana, isHiraganaOnly, splitIntoMoras } from "./mora.js";
import { loadWords, saveWords } from "./storage.js";

const state = {
  words: loadWords().map((word, index) => ({
    createdAt: new Date(index).toISOString(),
    ...word,
  })),
  query: "",
  bookmarkedOnly: false,
  sortMode: "reading",
};

let draftMoras = [];
let editingId = null;
let pendingDeleteAction = null;
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

/** アクセント辞典記法（上罫線・核の強調）でモーラ列を描画する。 */
function buildPitchNotation(moras) {
  const container = el("div", { className: "flex items-end gap-0.5" });
  moras.forEach((mora, index) => {
    const next = moras[index + 1];
    const isCore = mora.pitch === "H" && next && next.pitch === "L";
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

/** 読みからモーラ配列を再計算する。既存の並びと一致するモーラは高低指定を保持する。 */
function regenerateDraftMoras(reading) {
  const texts = splitIntoMoras(reading);
  draftMoras = texts.map((text, i) => ({
    text,
    pitch: draftMoras[i] && draftMoras[i].text === text ? draftMoras[i].pitch : "L",
  }));
}

function renderMoraEditor() {
  moraEditor.innerHTML = "";
  if (draftMoras.length === 0) {
    moraEditor.appendChild(
      el("p", {
        className: "text-xs text-gray-400",
        text: "読みを入力するとモーラが表示されます。",
      }),
    );
    return;
  }
  draftMoras.forEach((mora, index) => {
    const isHigh = mora.pitch === "H";
    const button = el("button", {
      className:
        "px-2 py-1 rounded-lg text-sm font-semibold border transition-colors " +
        (isHigh
          ? "bg-gray-900 text-white border-gray-900"
          : "bg-white text-gray-700 border-gray-300"),
      text: mora.text,
      attrs: {
        type: "button",
        "aria-pressed": String(isHigh),
        "aria-label": `${mora.text} を ${isHigh ? "高" : "低"} に設定中。クリックで切替`,
      },
    });
    button.addEventListener("click", () => {
      draftMoras[index].pitch = draftMoras[index].pitch === "H" ? "L" : "H";
      renderMoraEditor();
      renderPitchPreview();
    });
    moraEditor.appendChild(button);
  });
}

function renderPitchPreview() {
  pitchPreview.innerHTML = "";
  if (draftMoras.length === 0) return;
  pitchPreview.appendChild(buildPitchNotation(draftMoras));
}

function matchesFilters(word) {
  const query = state.query.trim();
  const matchesQuery =
    query === "" || word.word.includes(query) || word.reading.includes(query);
  const matchesBookmark = !state.bookmarkedOnly || word.bookmarked;
  return matchesQuery && matchesBookmark;
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
  checkbox.checked = selectedIds.has(word.id);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      selectedIds.add(word.id);
    } else {
      selectedIds.delete(word.id);
    }
    render();
  });
  card.appendChild(checkbox);

  const left = el("div", { className: "min-w-0" });
  const headerRow = el("div", { className: "flex items-baseline gap-2 flex-wrap" });
  headerRow.appendChild(el("span", { className: "font-bold", text: word.word }));
  headerRow.appendChild(el("span", { className: "text-xs text-gray-400", text: word.reading }));
  left.appendChild(headerRow);
  left.appendChild(buildPitchNotation(word.moras));
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
  bookmarkButton.addEventListener("click", () => {
    word.bookmarked = !word.bookmarked;
    saveWords(state.words);
    render();
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
    openDeleteConfirm(`「${word.word}」を削除しますか？`, () => {
      state.words = state.words.filter((w) => w.id !== word.id);
      saveWords(state.words);
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
    if (!state.words.some((w) => w.id === id)) selectedIds.delete(id);
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

  const allSelected = filtered.every((w) => selectedIds.has(w.id));
  selectAllCheckbox.checked = allSelected;
  selectAllCheckbox.indeterminate = count > 0 && !allSelected;
}

function render() {
  const filtered = state.words.filter(matchesFilters);
  if (state.sortMode === "createdAt") {
    filtered.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
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
  editingId = word.id;
  addWordHeading.textContent = "単語を編集";
  submitButton.textContent = "保存";
  clearFormError();
  wordInput.value = word.word;
  readingInput.value = word.reading;
  noteInput.value = word.note || "";
  draftMoras = word.moras.map((m) => ({ ...m }));
  renderMoraEditor();
  renderPitchPreview();
  addWordDialog.showModal();
  wordInput.focus();
}

function openDeleteConfirm(message, onConfirm) {
  pendingDeleteAction = onConfirm;
  deleteConfirmMessage.textContent = message;
  deleteConfirmDialog.showModal();
}

deleteConfirmOkButton.addEventListener("click", () => {
  const action = pendingDeleteAction;
  deleteConfirmDialog.close();
  if (action) action();
});
deleteConfirmCancelButton.addEventListener("click", () => deleteConfirmDialog.close());
deleteConfirmDialog.addEventListener("click", (event) => {
  if (event.target === deleteConfirmDialog) {
    deleteConfirmDialog.close();
  }
});
deleteConfirmDialog.addEventListener("close", () => {
  pendingDeleteAction = null;
});

openAddWordButton.addEventListener("click", openDialogForAdd);
closeAddWordButton.addEventListener("click", () => addWordDialog.close());
addWordDialog.addEventListener("click", (event) => {
  if (event.target === addWordDialog) {
    addWordDialog.close();
  }
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

wordForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const word = wordInput.value.trim();
  const reading = readingInput.value.trim();
  const note = noteInput.value.trim();

  if (!word || !reading) {
    showFormError("表記と読みは必須です。");
    return;
  }
  if (!isHiraganaOnly(reading)) {
    showFormError("読みはひらがなで入力してください。");
    return;
  }
  if (draftMoras.length === 0) {
    showFormError("読みを入力してください。");
    return;
  }
  const isDuplicate = state.words.some(
    (w) => w.id !== editingId && w.word === word && w.reading === reading,
  );
  if (isDuplicate) {
    showFormError("同じ表記・読みの単語が既に登録されています。");
    return;
  }

  if (editingId) {
    const target = state.words.find((w) => w.id === editingId);
    target.word = word;
    target.reading = reading;
    target.moras = draftMoras.map((m) => ({ ...m }));
    target.note = note;
  } else {
    state.words.push({
      id: crypto.randomUUID(),
      word,
      reading,
      moras: draftMoras.map((m) => ({ ...m })),
      note,
      bookmarked: false,
      createdAt: new Date().toISOString(),
    });
  }
  saveWords(state.words);
  addWordDialog.close();
  render();
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
    filtered.forEach((w) => selectedIds.add(w.id));
  } else {
    filtered.forEach((w) => selectedIds.delete(w.id));
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
  openDeleteConfirm(`選択した${count}件の単語を削除しますか？`, () => {
    state.words = state.words.filter((w) => !selectedIds.has(w.id));
    selectedIds.clear();
    saveWords(state.words);
    render();
  });
});

renderMoraEditor();
renderPitchPreview();
render();
