/**
 * Morphic-Agent Context Bridge — Background Service Worker
 *
 * Manifest v3 service worker. Handles:
 * - Extension install/update events
 * - Keyboard shortcut (Ctrl+Shift+M) opens the popup automatically
 *   via the _execute_action command defined in manifest.json
 */

"use strict";

// ---------------------------------------------------------------------------
// Install / Update
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    // Set default settings on first install
    chrome.storage.local.set({
      apiUrl: "http://localhost:8001",
      selectedPlatform: "claude_code",
    });

    console.log("[Morphic-Agent] Extension installed — defaults configured.");
  } else if (details.reason === "update") {
    console.log(
      `[Morphic-Agent] Extension updated to v${chrome.runtime.getManifest().version}`
    );
  }
});

// ---------------------------------------------------------------------------
// Message Handler (for future use — content script communication)
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "MORPHIC_HEALTH_CHECK") {
    // Forward health check request from content script
    fetch(message.apiUrl + "/api/health", {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    })
      .then((resp) => resp.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));

    // Return true to indicate async response
    return true;
  }

  if (message.type === "MORPHIC_EXPORT") {
    // Forward export request from content script
    const params = new URLSearchParams({
      platform: message.platform,
    });
    if (message.query) {
      params.set("q", message.query);
    }

    fetch(message.apiUrl + "/api/memory/export?" + params, {
      method: "GET",
      signal: AbortSignal.timeout(10000),
    })
      .then((resp) => resp.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));

    return true;
  }
});
