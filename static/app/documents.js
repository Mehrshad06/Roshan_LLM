import {api, byId, displayDate, element, faNumber, icon, showError} from "./common.js";

let documents = [];
let searchRequest;
let currentDocument = null;
let detailRequest;
const uploadPrompt = "فایل را انتخاب کنید یا اینجا رها کنید";

function fileInfo(filename) {
  const extension = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  const imageFile = ["png", "jpg", "jpeg"].includes(extension);
  return {format: imageFile ? "image" : extension, label: extension.toUpperCase() || "—"};
}

function documentRow(doc) {
  const row = element("tr");
  const nameCell = element("td");
  const link = element("button", "doc-link");
  link.type = "button";
  link.title = doc.title;
  link.addEventListener("click", () => openDocument(doc.id));
  const file = fileInfo(doc.filename);
  const stamp = element("span", "file-stamp", file.label);
  stamp.dataset.format = file.format;
  stamp.setAttribute("aria-hidden", "true");
  const label = element("span", "doc-label");
  const name = element("bdi", "doc-name", doc.title);
  const filename = element("bdi", "doc-filename", doc.filename);
  label.append(name, filename);
  link.append(stamp, label);
  nameCell.append(link);
  const type = element("td");
  type.append(element("span", "file-chip", file.label));
  const date = element("td", "date-cell", displayDate(doc.updated_at));
  const action = element("td");
  const open = element("button", "icon-button row-arrow");
  open.type = "button";
  open.setAttribute("aria-label", "مشاهدهٔ " + doc.title);
  open.append(icon("arrow"));
  open.addEventListener("click", () => openDocument(doc.id));
  action.append(open);
  row.append(nameCell, type, date, action);
  return row;
}

function renderDocuments() {
  const filter = byId("file-type").value;
  const visible = documents.filter((doc) => !filter || fileInfo(doc.filename).format === filter);
  byId("documents").replaceChildren(...visible.map(documentRow));
  const empty = byId("library-empty");
  empty.hidden = visible.length > 0;
  empty.textContent = byId("search").value.trim() || filter
    ? "سندی با این جست‌وجو و فیلتر پیدا نشد."
    : "هنوز سندی ندارید. برای شروع «افزودن سند» را انتخاب کنید.";
  byId("doc-count").textContent = faNumber.format(visible.length) + " سند";
}

async function loadDocuments() {
  searchRequest?.abort();
  searchRequest = new AbortController();
  showError("library-error");
  try {
    const query = new URLSearchParams({search: byId("search").value.trim()});
    documents = await api("/api/documents/?" + query, "GET", undefined, searchRequest.signal);
    renderDocuments();
  } catch (err) {
    if (err.name === "AbortError") return;
    byId("library-empty").hidden = true;
    showError("library-error", err.message);
  }
}

function setEditMode(mode) {
  const reading = mode === "read";
  const editing = mode === "edit";
  byId("detail-text").hidden = editing;
  byId("edit-form").hidden = !editing;
  byId("start-edit").hidden = !reading;
  byId("start-delete").hidden = !reading;
  byId("save-edit").hidden = !editing;
  byId("cancel-change").hidden = reading;
  byId("delete-warning").hidden = mode !== "delete";
  byId("confirm-delete").hidden = mode !== "delete";
  byId("detail-status").textContent = "";
  showError("detail-error");
}

function renderDetail(doc) {
  currentDocument = doc;
  byId("detail-title").textContent = doc.title;
  const filename = element("bdi", "", doc.filename);
  byId("detail-meta").replaceChildren(filename, " · آخرین ویرایش " + displayDate(doc.updated_at));
  byId("detail-text").replaceChildren(...doc.text.split(/\r?\n\s*\n/).map((part) => {
    const paragraph = element("p", "", part);
    paragraph.dir = "auto";
    return paragraph;
  }));
  byId("edit-name").value = doc.title;
  byId("edit-text").value = doc.text;
  setEditMode("read");
}

export async function openDocument(id) {
  const dialog = byId("detail-dialog");
  detailRequest?.abort();
  detailRequest = new AbortController();
  currentDocument = null;
  setEditMode("read");
  byId("detail-title").textContent = "مشاهدهٔ سند";
  byId("detail-meta").textContent = "";
  byId("detail-text").textContent = "در حال خواندن متن سند…";
  byId("start-edit").hidden = true;
  byId("start-delete").hidden = true;
  if (!dialog.open) dialog.showModal();
  try {
    const doc = await api("/api/documents/" + id + "/", "GET", undefined, detailRequest.signal);
    renderDetail(doc);
  } catch (err) {
    if (err.name === "AbortError") return;
    byId("detail-text").textContent = "";
    showError("detail-error", err.message);
  }
}

function busyDialog(id, busy) {
  const dialog = byId(id);
  dialog.setAttribute("aria-busy", String(busy));
  dialog.querySelectorAll("button, input, textarea").forEach((control) => {
    control.disabled = busy;
  });
}

async function changeDocument(method, data) {
  if (!currentDocument) return;
  busyDialog("detail-dialog", true);
  showError("detail-error");
  byId("detail-status").textContent = "در حال ثبت تغییرات…";
  try {
    const result = await api("/api/documents/" + currentDocument.id + "/", method, data);
    if (method === "DELETE") {
      byId("detail-dialog").close();
    } else {
      renderDetail(result);
    }
    await loadDocuments();
  } catch (err) {
    showError("detail-error", err.message);
  } finally {
    busyDialog("detail-dialog", false);
    byId("detail-status").textContent = "";
  }
}

function updateFileLabel() {
  byId("file-label").textContent = byId("upload-file").files[0]?.name || uploadPrompt;
}

async function uploadDocument(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  if (!data.get("title").trim()) data.delete("title");
  busyDialog("upload-dialog", true);
  byId("upload-status").textContent = "در حال استخراج متن و ساخت نمایه…";
  showError("upload-error");
  try {
    await api("/api/documents/", "POST", data);
    byId("upload-dialog").close();
    byId("search").value = "";
    byId("file-type").value = "";
    await loadDocuments();
  } catch (err) {
    showError("upload-error", err.message);
  } finally {
    byId("upload-status").textContent = "";
    busyDialog("upload-dialog", false);
  }
}

export function initDocuments() {
  let timeout;
  byId("search").addEventListener("input", () => {
    clearTimeout(timeout);
    searchRequest?.abort();
    timeout = setTimeout(loadDocuments, 240);
  });
  byId("file-type").addEventListener("change", renderDocuments);
  byId("add-document").addEventListener("click", () => {
    byId("upload-form").reset();
    updateFileLabel();
    showError("upload-error");
    byId("upload-dialog").showModal();
  });
  byId("upload-file").addEventListener("change", updateFileLabel);
  byId("upload-form").addEventListener("submit", uploadDocument);
  byId("detail-dialog").addEventListener("close", () => detailRequest?.abort());
  byId("start-edit").addEventListener("click", () => {
    setEditMode("edit");
    byId("edit-name").focus();
  });
  byId("start-delete").addEventListener("click", () => {
    setEditMode("delete");
    byId("cancel-change").focus();
  });
  byId("cancel-change").addEventListener("click", () => renderDetail(currentDocument));
  byId("confirm-delete").addEventListener("click", () => changeDocument("DELETE"));
  byId("edit-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const changes = {};
    if (byId("edit-name").value !== currentDocument.title) changes.title = byId("edit-name").value;
    if (byId("edit-text").value !== currentDocument.text) changes.text = byId("edit-text").value;
    if (Object.keys(changes).length) changeDocument("PATCH", changes);
    else setEditMode("read");
  });
  loadDocuments();
}
