/* TEST ONLY — NON-DISTRIBUTABLE. Native buttons remain keyboard operable. */
"use strict";

const statusNode = document.getElementById("state");
const exportNode = document.getElementById("export");

for (const button of document.querySelectorAll("button[data-action]")) {
  button.addEventListener("click", () => {
    chrome.runtime.sendMessage({kind: "XFI_CONTROL", action: button.dataset.action}, (response) => {
      const reply = response && response.ok ? response.reply : null;
      globalThis.__XFI_CONTROL_LAST__ = {response, reply};
      const snapshot = reply && reply.snapshot;
      statusNode.textContent = "State: " + (snapshot ? snapshot.state : "ERROR") + (response && response.code ? " (" + response.code + ")" : "");
      if (reply && reply.result && typeof reply.result === "object" && reply.result.schema_version) {
        exportNode.textContent = JSON.stringify(reply.result, null, 2);
        exportNode.hidden = false;
      }
    });
  });
}
