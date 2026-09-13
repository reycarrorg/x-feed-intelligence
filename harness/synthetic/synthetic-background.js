/* TEST ONLY — NON-DISTRIBUTABLE. Routes explicit popup controls to one reserved-origin fixture tab. */
"use strict";

let fixtureTabId = null;

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message && message.kind === "XFI_REGISTER_FIXTURE" && sender.tab && sender.tab.id !== undefined && sender.url === "https://fixture.example.invalid/") {
    fixtureTabId = sender.tab.id;
    respond({ok: true});
    return false;
  }
  if (!message || message.kind !== "XFI_CONTROL" || sender.id !== chrome.runtime.id || !sender.url || !sender.url.startsWith(chrome.runtime.getURL(""))) {
    respond({ok: false, code: "CONTROL_SENDER_REJECTED"});
    return false;
  }
  if (fixtureTabId === null) {
    respond({ok: false, code: "FIXTURE_TAB_UNAVAILABLE"});
    return false;
  }
  chrome.tabs.sendMessage(fixtureTabId, {action: message.action}, (reply) => {
    if (chrome.runtime.lastError) respond({ok: false, code: "FIXTURE_TAB_UNAVAILABLE"});
    else respond({ok: true, reply});
  });
  return true;
});
