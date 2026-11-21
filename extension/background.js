// Advanced App Tracker: sends the active tab to the local app (Firefox).
// Everything stays on this computer: the only address used is 127.0.0.1.

const API_BASE = "http://127.0.0.1:8765";
const BROWSER_NAME = "firefox";
const SESSION_KEY = "currentSession";

// After this many seconds without mouse/keyboard input the user counts as away.
const IDLE_SECONDS = 60;
// Once a minute: re-check idle state and remind the app about the open session.
const HEARTBEAT_ALARM = "heartbeat";

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

// A tab that plays sound (a video, a lecture) counts as "in use"
// even when the mouse and keyboard are not touched.
async function isAudible(tabId) {
  try {
    const tab = await browser.tabs.get(tabId);
    return Boolean(tab.audible);
  } catch (error) {
    return false;
  }
}

async function isUserActive() {
  try {
    return (await browser.idle.queryState(IDLE_SECONDS)) === "active";
  } catch (error) {
    return true;
  }
}

function sendStart(session) {
  return post("/browser-event/start", {
    session_id: session.sessionId,
    browser: BROWSER_NAME,
    url: session.url,
    title: session.title,
    started_at: session.startedAt,
    window_id: session.windowId,
    tab_id: session.tabId,
  });
}

// backSeconds: how long the user was already away when we noticed it.
// That time is not counted.
async function stopCurrent(reason, backSeconds = 0) {
  const session = await loadSession();
  if (!session) return;
  await saveSession(null);
  const startedMs = Date.parse(session.startedAt) || Date.now();
  const endedMs = Math.max(startedMs, Date.now() - backSeconds * 1000);
  await post("/browser-event/stop", {
    session_id: session.sessionId,
    ended_at: new Date(endedMs).toISOString(),
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
  // Do not start while the user is away (for example autoplay of the next video).
  if (!(await isUserActive()) && !tab.audible) return;

  const fresh = {
    sessionId: crypto.randomUUID(),
    tabId: tab.id,
    windowId: tab.windowId,
    url: tab.url,
    title: tab.title || "",
    startedAt: new Date().toISOString(),
  };
  await saveSession(fresh);
  await sendStart(fresh);
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

// Start tracking the current tab (startup, coming back from idle).
async function syncCurrent(reason = "startup") {
  const win = await browser.windows.getLastFocused();
  if (!win.focused) return;
  const tabs = await browser.tabs.query({ active: true, windowId: win.id });
  await startFor(tabs[0], reason);
}

// The user went away or came back.
async function onIdleState(state) {
  if (state === "active") {
    await syncCurrent("idle_end");
    return;
  }
  const session = await loadSession();
  if (!session) return;
  if (state === "idle" && (await isAudible(session.tabId))) return;
  // "idle" is reported IDLE_SECONDS after the last input; "locked" right away.
  await stopCurrent("idle", state === "idle" ? IDLE_SECONDS : 0);
}

// Runs once a minute.
async function heartbeat() {
  const session = await loadSession();
  if (!session) {
    if (await isUserActive()) await syncCurrent("heartbeat");
    return;
  }
  if (!(await isUserActive()) && !(await isAudible(session.tabId))) {
    // Sound stopped while the user was away (the video ended).
    await stopCurrent("idle", IDLE_SECONDS);
    return;
  }
  // If the desktop app was restarted, it forgot the open session.
  // Sending "start" again is safe: the app ignores a session it already has.
  await sendStart(session);
}

browser.idle.setDetectionInterval(IDLE_SECONDS);
browser.idle.onStateChanged.addListener((state) => enqueue(() => onIdleState(state)));

browser.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: 1 });
browser.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEARTBEAT_ALARM) enqueue(heartbeat);
});

browser.runtime.onStartup.addListener(() => enqueue(() => syncCurrent("startup")));
browser.runtime.onInstalled.addListener(() => enqueue(() => syncCurrent("startup")));
