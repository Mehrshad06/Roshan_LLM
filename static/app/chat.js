import {api, byId, displayDate, element, faNumber, icon, showError} from "./common.js";
import {openDocument} from "./documents.js";

const conversationsUrl = "/api/conversations/";
const storageKey = "sandyar.conversation." + document.querySelector(".shell").dataset.userId;
let current = null;
let pending = false;
let generating = null;
let editing = null;

function remember(id) {
  try { localStorage.setItem(storageKey, String(id)); } catch { /* Storage is optional. */ }
}

function lastConversation() {
  try { return localStorage.getItem(storageKey); } catch { return null; }
}

function setPending(value) {
  pending = value;
  for (const id of ["question", "send", "history", "new-chat"]) byId(id).disabled = value;
  byId("ask-form").setAttribute("aria-busy", String(value));
}

function scrollToLatest() {
  const area = byId("chat-scroll");
  area.scrollTop = area.scrollHeight;
}

function sourceList(sources) {
  const details = element("details", "sources");
  details.append(element("summary", "", gettext("منابع پاسخ (") + faNumber.format(sources.length) + ")"));
  for (const [index, item] of sources.entries()) {
    const source = element("div", "source");
    const title = element("button", "", item.title);
    title.type = "button";
    title.dir = "auto";
    title.title = gettext("مشاهدهٔ سند منبع");
    title.addEventListener("click", () => openDocument(item.document_id, item.quote));
    const location = element("small", "", item.location.replace(/^Page (\d+)/, gettext("صفحهٔ $1"))
      .replace("Document body", gettext("متن اصلی سند")).replace(" · Row ", gettext(" · ردیف ")));
    location.dir = "auto";
    const quote = element("blockquote", "", item.quote);
    quote.dir = "auto";
    source.append(element("span", "citation-number", faNumber.format(index + 1)), title, location);
    if (item.filename) source.append(element("small", "source-file", item.filename));
    source.append(quote);
    details.append(source);
  }
  return details;
}

function message(role, text, sources = []) {
  const row = element("div", "message " + role + "-message");
  const bubble = element("div", "bubble", text);
  bubble.dir = "auto";
  row.append(element("span", "message-label", role === "user" ? gettext("شما") : gettext("سندیار")), bubble);
  if (sources.length) {
    const details = sourceList(sources);
    const cards = details.querySelectorAll(".source button");
    row.append(details);
    bubble.replaceChildren();
    for (const part of text.split(/(\[\d+\])/)) {
      const number = /^\[(\d+)\]$/.exec(part);
      const card = number && cards[Number(number[1]) - 1];
      if (card) {
        const link = element("button", "turn-edit", part);
        link.type = "button";
        link.setAttribute("aria-label", gettext("مشاهدهٔ منبع ") + number[1]);
        link.onclick = () => { details.open = true; card.focus(); };
        bubble.append(link);
      } else {
        bubble.append(part);
      }
    }
  }
  return row;
}

function renderTurns(turns) {
  const nodes = [];
  for (const turn of turns) {
    const userMessage = message("user", turn.question);
    if (turn === turns.at(-1)) {
      const edit = element("button", "turn-edit", gettext("ویرایش پیام"));
      edit.type = "button";
      edit.onclick = () => {
        if (pending) return;
        editing = turn.id;
        byId("edit-notice").hidden = false;
        byId("question").value = turn.question;
        byId("question").focus();
      };
      userMessage.append(edit);
    }
    nodes.push(userMessage, message("assistant", turn.answer, turn.sources));
  }
  byId("messages").replaceChildren(...nodes);
  byId("chat-welcome").hidden = turns.length > 0;
  scrollToLatest();
}

function selectConversation(record) {
  editing = null;
  byId("edit-notice").hidden = true;
  current = record;
  byId("conversation-title").textContent = record?.title || gettext("گفت‌وگوی جدید");
  byId("conversation-title").dir = "auto";
  byId("question").value = "";
  remember(record?.id ?? "new");
  showError("chat-error");
  renderTurns(record?.turns || []);
}

async function openConversation(id) {
  setPending(true);
  try {
    selectConversation(await api(conversationsUrl + id + "/"));
  } catch (err) {
    showError("chat-error", err.message);
  } finally {
    setPending(false);
  }
}

async function showHistory() {
  const dialog = byId("history-dialog");
  const list = byId("history-list");
  list.textContent = gettext("در حال خواندن تاریخچه…");
  dialog.showModal();
  try {
    const conversations = await api(conversationsUrl);
    list.replaceChildren();
    if (!conversations.length) list.textContent = gettext("هنوز گفت‌وگویی ثبت نشده است.");
    conversations.forEach((record) => {
      const button = element("button", "history-item");
      button.type = "button";
      const label = element("span", "history-label");
      const title = element("bdi", "history-name", record.title || gettext("گفت‌وگوی جدید"));
      label.append(title, element("small", "muted", displayDate(record.created_at)));
      button.append(icon("chat"), label, icon("arrow"));
      button.addEventListener("click", () => {
        dialog.close();
        openConversation(record.id);
      });
      list.append(button);
    });
  } catch (err) {
    list.textContent = err.message;
  }
}

async function ask(event) {
  event.preventDefault();
  const input = byId("question");
  const question = input.value.trim();
  if (pending || !question) return;
  showError("chat-error");
  setPending(true);
  input.value = "";
  byId("chat-welcome").hidden = true;
  const waiting = message("assistant", gettext("در حال جست‌وجو در اسناد و آماده‌سازی پاسخ…"));
  byId("messages").append(message("user", question), waiting);
  scrollToLatest();
  try {
    if (!current) {
      current = await api(conversationsUrl, "POST", {});
      current.turns = [];
      remember(current.id);
    }
    const base = conversationsUrl + current.id + "/";
    generating = new AbortController();
    byId("cancel-answer").hidden = false;
    const preview = await api(base + "preview/", "POST", {question, replace_id: editing}, generating.signal);
    generating = null;
    byId("cancel-answer").hidden = true;
    const turn = await api(base + "confirm/", "POST", {ticket: preview.ticket});
    if (editing) current.turns.pop();
    editing = null;
    byId("edit-notice").hidden = true;
    current.turns.push(turn);
    if (current.turns.length === 1) byId("conversation-title").textContent = question;
    renderTurns(current.turns);
  } catch (err) {
    input.value = question;
    renderTurns(current?.turns || []);
    if (err.name !== "AbortError") showError("chat-error", err.message);
  } finally {
    generating = null;
    byId("cancel-answer").hidden = true;
    setPending(false);
    input.focus();
  }
}

async function restoreConversation() {
  const selected = lastConversation();
  if (selected === "new") return;
  setPending(true);
  try {
    const records = await api(conversationsUrl);
    const target = records.find((item) => String(item.id) === selected) || records[0];
    if (target) selectConversation(await api(conversationsUrl + target.id + "/"));
  } catch (err) {
    showError("chat-error", err.message);
  } finally {
    setPending(false);
  }
}

export function initChat() {
  byId("cancel-answer").onclick = () => generating?.abort();
  byId("discard-edit").onclick = () => {
    if (pending) return;
    editing = null;
    byId("edit-notice").hidden = true;
    byId("question").value = "";
  };
  byId("history").addEventListener("click", showHistory);
  byId("new-chat").addEventListener("click", () => {
    selectConversation(null);
    byId("question").focus();
  });
  byId("ask-form").addEventListener("submit", ask);
  byId("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      byId("ask-form").requestSubmit();
    }
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      byId("question").value = button.dataset.question;
      byId("question").focus();
    });
  });
  restoreConversation();
}
