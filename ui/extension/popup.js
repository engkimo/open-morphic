/**
 * Morphic-Agent Context Bridge — Popup Script
 *
 * Communicates with the Morphic-Agent backend to export context
 * formatted for different AI platforms, then copies to clipboard.
 */

"use strict";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_API_URL = "http://localhost:8001";
const HEALTH_ENDPOINT = "/api/health";
const EXPORT_ENDPOINT = "/api/memory/export";
const HEALTH_CHECK_INTERVAL = 15000; // 15s

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------

const $statusDot = document.getElementById("statusDot");
const $connectionBanner = document.getElementById("connectionBanner");
const $platform = document.getElementById("platform");
const $query = document.getElementById("query");
const $exportBtn = document.getElementById("exportBtn");
const $loading = document.getElementById("loading");
const $statusMsg = document.getElementById("statusMsg");
const $resultArea = document.getElementById("resultArea");
const $resultPreview = document.getElementById("resultPreview");
const $tokenBadge = document.getElementById("tokenBadge");
const $copyBtn = document.getElementById("copyBtn");
const $clearBtn = document.getElementById("clearBtn");
const $settingsPanel = document.getElementById("settingsPanel");
const $settingsToggle = document.getElementById("settingsToggle");
const $apiUrl = document.getElementById("apiUrl");
const $saveSettingsBtn = document.getElementById("saveSettingsBtn");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let apiUrl = DEFAULT_API_URL;
let isConnected = false;
let lastExportedContent = "";
let healthCheckTimer = null;

// ---------------------------------------------------------------------------
// Storage Helpers
// ---------------------------------------------------------------------------

async function loadSettings() {
  try {
    const data = await chrome.storage.local.get([
      "apiUrl",
      "selectedPlatform",
    ]);
    if (data.apiUrl) {
      apiUrl = data.apiUrl;
      $apiUrl.value = apiUrl;
    } else {
      $apiUrl.value = DEFAULT_API_URL;
    }
    if (data.selectedPlatform) {
      $platform.value = data.selectedPlatform;
    }
  } catch {
    // storage unavailable (e.g. running outside extension context)
    $apiUrl.value = DEFAULT_API_URL;
  }
}

async function savePlatform(platform) {
  try {
    await chrome.storage.local.set({ selectedPlatform: platform });
  } catch {
    // ignore
  }
}

async function saveApiUrl(url) {
  try {
    await chrome.storage.local.set({ apiUrl: url });
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Connection Check
// ---------------------------------------------------------------------------

async function checkHealth() {
  $statusDot.className = "status-dot checking";
  $statusDot.title = "Checking connection...";

  try {
    const resp = await fetch(`${apiUrl}${HEALTH_ENDPOINT}`, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data.status === "ok") {
        setConnected(true);
        return;
      }
    }
    setConnected(false);
  } catch {
    setConnected(false);
  }
}

function setConnected(connected) {
  isConnected = connected;
  if (connected) {
    $statusDot.className = "status-dot connected";
    $statusDot.title = "Connected to Morphic-Agent backend";
    $connectionBanner.classList.remove("visible");
    $exportBtn.disabled = false;
  } else {
    $statusDot.className = "status-dot";
    $statusDot.title = "Backend offline";
    $connectionBanner.classList.add("visible");
    $exportBtn.disabled = true;
  }
}

// ---------------------------------------------------------------------------
// Status Messages
// ---------------------------------------------------------------------------

function showStatus(message, type) {
  $statusMsg.textContent = message;
  $statusMsg.className = `status-msg visible ${type}`;
  if (type === "success") {
    setTimeout(() => {
      $statusMsg.classList.remove("visible");
    }, 3000);
  }
}

function hideStatus() {
  $statusMsg.classList.remove("visible");
}

// ---------------------------------------------------------------------------
// Export Context
// ---------------------------------------------------------------------------

async function exportContext() {
  const platform = $platform.value;
  const query = $query.value.trim();

  // Save selected platform
  savePlatform(platform);

  // UI: show loading
  $exportBtn.disabled = true;
  $loading.classList.add("visible");
  $resultArea.classList.remove("visible");
  hideStatus();

  try {
    const params = new URLSearchParams({ platform });
    if (query) {
      params.set("q", query);
    }

    const resp = await fetch(`${apiUrl}${EXPORT_ENDPOINT}?${params}`, {
      method: "GET",
      signal: AbortSignal.timeout(10000),
    });

    if (!resp.ok) {
      const errText = await resp.text().catch(() => "Unknown error");
      throw new Error(`HTTP ${resp.status}: ${errText}`);
    }

    const data = await resp.json();

    lastExportedContent = data.content || "";
    const tokenEstimate = data.token_estimate || 0;

    // UI: show result
    $resultPreview.textContent = truncatePreview(lastExportedContent, 500);
    $tokenBadge.textContent = `${tokenEstimate.toLocaleString()} tokens`;
    $resultArea.classList.add("visible");
    showStatus(`Exported for ${formatPlatformName(platform)}`, "success");
  } catch (err) {
    if (err.name === "AbortError" || err.name === "TimeoutError") {
      showStatus("Request timed out — is the backend running?", "error");
    } else {
      showStatus(err.message || "Export failed", "error");
    }
    // Re-check connection
    checkHealth();
  } finally {
    $loading.classList.remove("visible");
    $exportBtn.disabled = !isConnected;
  }
}

// ---------------------------------------------------------------------------
// Copy to Clipboard
// ---------------------------------------------------------------------------

async function copyToClipboard() {
  if (!lastExportedContent) return;

  try {
    await navigator.clipboard.writeText(lastExportedContent);
    showStatus("Copied to clipboard", "success");

    // Visual feedback on button
    const originalText = $copyBtn.innerHTML;
    $copyBtn.innerHTML = '<span class="btn-icon">&#x2713;</span> Copied';
    setTimeout(() => {
      $copyBtn.innerHTML = originalText;
    }, 1500);
  } catch (err) {
    showStatus("Failed to copy: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncatePreview(text, maxLen) {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "\n\n... (truncated)";
}

function formatPlatformName(platform) {
  const names = {
    claude_code: "Claude Code",
    chatgpt: "ChatGPT",
    cursor: "Cursor",
    gemini: "Gemini",
  };
  return names[platform] || platform;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

function toggleSettings() {
  const isVisible = $settingsPanel.classList.contains("visible");
  if (isVisible) {
    $settingsPanel.classList.remove("visible");
    $settingsToggle.textContent = "Settings";
  } else {
    $settingsPanel.classList.add("visible");
    $settingsToggle.textContent = "Hide Settings";
    $apiUrl.value = apiUrl;
  }
}

async function saveSettings() {
  const newUrl = $apiUrl.value.trim().replace(/\/+$/, "");
  if (!newUrl) {
    showStatus("API URL cannot be empty", "error");
    return;
  }
  apiUrl = newUrl;
  await saveApiUrl(apiUrl);
  showStatus("Settings saved", "success");
  $settingsPanel.classList.remove("visible");
  $settingsToggle.textContent = "Settings";
  // Re-check with new URL
  checkHealth();
}

// ---------------------------------------------------------------------------
// Clear
// ---------------------------------------------------------------------------

function clearResult() {
  lastExportedContent = "";
  $resultArea.classList.remove("visible");
  hideStatus();
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

$exportBtn.addEventListener("click", exportContext);
$copyBtn.addEventListener("click", copyToClipboard);
$clearBtn.addEventListener("click", clearResult);
$settingsToggle.addEventListener("click", toggleSettings);
$saveSettingsBtn.addEventListener("click", saveSettings);

// Enter key triggers export from query field
$query.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !$exportBtn.disabled) {
    exportContext();
  }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

(async function init() {
  await loadSettings();
  await checkHealth();

  // Periodic health check
  healthCheckTimer = setInterval(checkHealth, HEALTH_CHECK_INTERVAL);
})();
