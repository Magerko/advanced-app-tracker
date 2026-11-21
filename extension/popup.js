// Small window that opens when you click the extension icon.
// Shows whether the desktop app is running and which site is being recorded.

const API_BASE = "http://127.0.0.1:8765";

const statusEl = document.getElementById("status");
const siteEl = document.getElementById("site");

function show(text, ok) {
  statusEl.textContent = text;
  statusEl.className = "status " + (ok ? "ok" : "bad");
}

async function checkApi() {
  try {
    const response = await fetch(API_BASE + "/health");
    const data = await response.json();
    if (data.status === "ok") {
      show("Трекер запущен, сайты записываются", true);
    } else {
      show("Трекер ответил с ошибкой", false);
    }
  } catch (error) {
    show("Трекер не запущен", false);
  }
}

async function showCurrentSite() {
  const data = await browser.storage.session.get("currentSession");
  const session = data.currentSession;
  if (session) {
    siteEl.textContent = "Сейчас: " + new URL(session.url).hostname;
  } else {
    siteEl.textContent = "Сейчас ничего не записывается";
  }
}

checkApi();
showCurrentSite();
