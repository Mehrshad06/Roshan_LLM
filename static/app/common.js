export const byId = (id) => document.getElementById(id);
export const faNumber = new Intl.NumberFormat("fa-IR");
const dateFormat = new Intl.DateTimeFormat("fa-IR", {year: "numeric", month: "2-digit", day: "2-digit"});

export function displayDate(value) {
  return value ? dateFormat.format(new Date(value)) : "—";
}

// Put all API text in text nodes, including uploaded text and model output.
export function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = value;
  return node;
}

export function icon(name) {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(namespace, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

export function showError(id, message = "") {
  const box = byId(id);
  box.textContent = message;
  box.hidden = !message;
}

function errorText(payload) {
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload)) return payload.map(errorText).join(" ");
  if (payload && typeof payload === "object") {
    return Object.entries(payload).map(([key, value]) => {
      const labels = {title: "عنوان", text: "متن سند", file: "فایل", question: "پرسش"};
      return (labels[key] ? labels[key] + " — " : "") + errorText(value);
    }).join("\n");
  }
  return "";
}

export async function api(path, method = "GET", data, signal) {
  const headers = {Accept: "application/json"};
  let body;
  if (method !== "GET") {
    headers["X-CSRFToken"] = document.querySelector("[name=csrfmiddlewaretoken]").value;
    if (data instanceof FormData) {
      body = data;
    } else if (data !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(data);
    }
  }
  let response;
  try {
    response = await fetch(path, {method, body, headers, signal, credentials: "same-origin"});
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("ارتباط با سرور برقرار نشد. اتصال را بررسی و دوباره تلاش کنید.");
  }
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload === null) {
    const message = errorText(payload) || "درخواست انجام نشد. دوباره تلاش کنید.";
    throw new Error(message);
  }
  return payload;
}
