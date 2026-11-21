import {byId} from "./common.js";
import {initDocuments} from "./documents.js";
import {initChat} from "./chat.js";

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("cancel", (event) => {
    if (dialog.getAttribute("aria-busy") === "true") event.preventDefault();
  });
});
document.querySelectorAll("[data-pane]").forEach((button) => {
  button.addEventListener("click", () => {
    const pane = button.dataset.pane;
    document.querySelector(".workspace").dataset.visible = pane;
    document.querySelectorAll("[data-pane]").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    if (pane === "chat") {
      const area = byId("chat-scroll");
      area.scrollTop = area.scrollHeight;
    }
  });
});

initDocuments();
initChat();
import "./graph.js";
