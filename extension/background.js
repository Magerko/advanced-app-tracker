// Advanced App Tracker: sends the active tab to the local app (Firefox).
// Everything stays on this computer: the only address used is 127.0.0.1.

const API_BASE = "http://127.0.0.1:8765";
const BROWSER_NAME = "firefox";
const SESSION_KEY = "currentSession";

// Events can arrive very close together. Handle them one after another.
let queue = Promise.resolve();
function enqueue(task) {
  queue = queue.then(task).catch((error) => console.debug("tracker:", error));
  return queue;
}

async function post(path, body) {
  try {
    await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    // The desktop app is closed. That is fine, stay silent.
  }
}

// The background page can be put to sleep by Firefox, so the current
// session is kept in storage.session instead of a plain variable.
async function loadSession() {
  const data = await browser.storage.session.get(SESSION_KEY);
  return data[SESSION_KEY] || null;
}

async function saveSession(session) {
  if (session) {
    await browser.storage.session.set({ [SESSION_KEY]: session });
  } else {
    await browser.storage.session.remove(SESSION_KEY);
  }
}

function isTrackable(tab) {
  return Boolean(tab) && !tab.incognito && /^https?:\/\//i.test(tab.url || "");
}

function stripHash(url) {
  return (url || "").split("#")[0];
}

async function isWindowFocused(windowId) {
  try {
    const win = await browser.windows.get(windowId);
    return win.focused;
  } catch (error) {
    return false;
  }
}

async function stopCurrent(reason) {
  const session = await loadSession();
  if (!session) return;
  await saveSession(null);
  await post("/browser-event/stop", {
    session_id: session.sessionId,
    ended_at: new Date().toISOString(),
    reason: reason,
  });
}

async function startFor(tab, reason) {
  const session = await loadSession();
  if (
    session &&
    tab &&
    session.tabId === tab.id &&
    stripHash(session.url) === stripHash(tab.url)
  ) {
    return; // already tracking exactly this page
  }

  await stopCurrent(reason);
  if (!isTrackable(tab)) return;

  const fresh = {
    sessionId: crypto.randomUUID(),
    tabId: tab.id,
    url: tab.url,
    title: tab.title || "",
  };
  await saveSession(fresh);
  await post("/browser-event/start", {
    session_id: fresh.sessionId,
    browser: BROWSER_NAME,
    url: fresh.url,
    title: fresh.title,
    started_at: new Date().toISOString(),
    window_id: tab.windowId,
    tab_id: tab.id,
  });
}

// The user switched to another tab.
browser.tabs.onActivated.addListener((info) => {
  enqueue(async () => {
    let tab = null;
    try {
      tab = await browser.tabs.get(info.tabId);
    } catch (error) {
      return;
    }
    if (!(await isWindowFocused(tab.windowId))) return;
    await startFor(tab, "tab_switch");
  });
});

// The address or the title of a tab changed.
browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  enqueue(async () => {
    if (changeInfo.url !== undefined) {
      if (!tab.active) return;
      if (!(await isWindowFocused(tab.windowId))) return;
      await startFor(tab, "url_change");
      return;
    }
    if (changeInfo.title !== undefined) {
      const session = await loadSession();
      if (!session || session.tabId !== tabId) return;
      session.title = tab.title || "";
      await saveSession(session);
      await post("/browser-event/update-title", {
        session_id: session.sessionId,
        title: session.title,
      });
    }
  });
});

// A tab was closed.
browser.tabs.onRemoved.addListener((tabId) => {
  enqueue(async () => {
    const session = await loadSession();
    if (session && session.tabId === tabId) {
      await stopCurrent("tab_closed");
    }
  });
});

// The browser window got or lost focus.
browser.windows.onFocusChanged.addListener((windowId) => {
  enqueue(async () => {
    if (windowId === browser.windows.WINDOW_ID_NONE) {
      await stopCurrent("window_blur");
      return;
    }
    const tabs = await browser.tabs.query({ active: true, windowId: windowId });
    await startFor(tabs[0], "window_focus");
  });
});

// Start tracking the current tab when Firefox or the extension starts.
async function syncCurrent() {
  const win = await browser.windows.getLastFocused();
  if (!win.focused) return;
  const tabs = await browser.tabs.query({ active: true, windowId: win.id });
  await startFor(tabs[0], "startup");
}

browser.runtime.onStartup.addListener(() => enqueue(syncCurrent));
browser.runtime.onInstalled.addListener(() => enqueue(syncCurrent));
