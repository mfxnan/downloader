const urlInput = document.getElementById("video-url");
const analyzeButton = document.getElementById("analyze-btn");
const loading = document.getElementById("loading");
const result = document.getElementById("result");
const thumbnail = document.getElementById("thumbnail");
const title = document.getElementById("title");
const platform = document.getElementById("platform");
const uploader = document.getElementById("uploader");
const duration = document.getElementById("duration");
const qualitySelect = document.getElementById("quality-select");
const downloadButton = document.getElementById("download-btn");
const bulkUrls = document.getElementById("bulk-urls");
const bulkCheckButton = document.getElementById("bulk-check-btn");
const bulkDownloadButton = document.getElementById("bulk-download-btn");
const bulkStatus = document.getElementById("bulk-status");
const historyList = document.getElementById("history-list");
const clearHistoryButton = document.getElementById("clear-history");
const defaultFormatSelect = document.getElementById("default-format");
const themeSelect = document.getElementById("theme-select");
const serviceStatus = document.getElementById("service-status");

const HISTORY_KEY = "dl-repostium-history";
const SETTINGS_KEY = "dl-repostium-settings";
const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 60 * 60;

let currentURL = "";
let currentTitle = "";
let currentPlatform = "";

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "-";
  }

  const totalSeconds = Math.floor(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  }

  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function setHidden(element, hidden) {
  element.classList.toggle("hidden", hidden);
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || `Request failed (${response.status}).`);
  }

  return data;
}

function getSettings() {
  const stored = localStorage.getItem(SETTINGS_KEY);
  if (!stored) {
    return {};
  }

  try {
    return JSON.parse(stored);
  } catch {
    localStorage.removeItem(SETTINGS_KEY);
    return {};
  }
}

function saveSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    defaultFormat: defaultFormatSelect.value,
    theme: themeSelect.value,
  }));
}

function applySettings() {
  const settings = getSettings();
  defaultFormatSelect.value = settings.defaultFormat === "audio" ? "audio" : "video";
  themeSelect.value = settings.theme === "midnight" ? "midnight" : "dark";
  qualitySelect.value = defaultFormatSelect.value === "audio" ? "audio" : "best";
  document.body.dataset.theme = themeSelect.value;
}

function readHistory() {
  const stored = localStorage.getItem(HISTORY_KEY);
  if (!stored) {
    return [];
  }

  try {
    const history = JSON.parse(stored);
    return Array.isArray(history) ? history : [];
  } catch {
    localStorage.removeItem(HISTORY_KEY);
    return [];
  }
}

function renderHistory() {
  const history = readHistory();
  historyList.replaceChildren();

  if (history.length === 0) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "No downloads yet.";
    historyList.appendChild(emptyItem);
    return;
  }

  history.forEach((item) => {
    const entry = document.createElement("li");
    const name = document.createElement("strong");
    const details = document.createElement("span");
    name.textContent = item.title || item.url;
    details.textContent = `${item.mode === "audio" ? "Audio" : "Video"} · ${new Date(item.downloadedAt).toLocaleString()}`;
    entry.append(name, details);
    historyList.appendChild(entry);
  });
}

function addToHistory(item) {
  const history = readHistory();
  history.unshift({ ...item, downloadedAt: Date.now() });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 20)));
  renderHistory();
}

function getBulkUrls() {
  return bulkUrls.value
    .split(/\r?\n/)
    .map((url) => url.trim())
    .filter(Boolean);
}

function findDuplicates(urls) {
  const seen = new Set();
  const duplicates = new Set();

  urls.forEach((url) => {
    if (seen.has(url)) {
      duplicates.add(url);
    }
    seen.add(url);
  });

  return duplicates;
}

function setBulkMessage(message, type = "") {
  bulkStatus.textContent = message;
  bulkStatus.dataset.state = type;
}

async function analyzeURL() {
  const url = urlInput.value.trim();
  if (!url) {
    alert("Please enter a media URL first.");
    return;
  }

  currentURL = url;
  currentTitle = "";
  currentPlatform = "";
  setHidden(result, true);
  setHidden(loading, false);
  loading.textContent = "Fetching media information…";
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyzing…";

  try {
    const data = await requestJson("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    currentTitle = data.title || "";
    currentPlatform = data.platform || "";
    title.textContent = data.title || "Untitled media";
    platform.textContent = data.platform ? `Platform: ${data.platform}` : "";
    uploader.textContent = `Uploader: ${data.uploader || "Unknown"}`;
    duration.textContent = `Duration: ${formatDuration(data.duration)}`;

    if (data.thumbnail) {
      thumbnail.src = data.thumbnail;
      thumbnail.alt = data.title ? `Thumbnail for ${data.title}` : "Media thumbnail";
      thumbnail.classList.remove("hidden");
    } else {
      thumbnail.removeAttribute("src");
      thumbnail.classList.add("hidden");
    }

    setHidden(loading, true);
    setHidden(result, false);
  } catch (error) {
    setHidden(loading, true);
    setHidden(result, true);
    alert(error.message);
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.textContent = "Analyze";
  }
}

function saveBlob(blob, filename) {
  const objectURL = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectURL;
  link.download = filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function downloadJob(jobId, url, name, mode, onStatus = () => {}) {
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
    const status = await requestJson(`/api/status/${encodeURIComponent(jobId)}`);
    onStatus(status.status);

    if (status.status === "failed") {
      throw new Error(status.error || "The download failed.");
    }

    if (status.status === "completed") {
      const response = await fetch(`/api/file/${encodeURIComponent(jobId)}`);
      if (!response.ok) {
        let detail = `Could not retrieve the downloaded file (${response.status}).`;
        try {
          const error = await response.json();
          detail = error.detail || detail;
        } catch {
          // Keep the HTTP status message when the response is not JSON.
        }
        throw new Error(detail);
      }

      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = disposition.match(/filename="([^"]+)"/i)?.[1] || name || "download";
      saveBlob(await response.blob(), filename);
      addToHistory({ title: name || url, url, mode });
      return;
    }

    await wait(POLL_INTERVAL_MS);
  }

  throw new Error("The download took too long. Check the server and try again.");
}

async function downloadCurrent() {
  if (!currentURL) {
    return;
  }

  const mode = qualitySelect.value === "audio" ? "audio" : "video";
  downloadButton.disabled = true;
  downloadButton.textContent = "Starting…";

  try {
    const job = await requestJson("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentURL, mode }),
    });

    downloadButton.textContent = "Downloading…";
    await downloadJob(job.job_id, currentURL, currentTitle, mode, (status) => {
      downloadButton.textContent = status === "queued" ? "Queued…" : "Downloading…";
    });
    downloadButton.textContent = "Downloaded";
  } catch (error) {
    alert(error.message);
    downloadButton.textContent = "Download";
  } finally {
    downloadButton.disabled = false;
  }
}

async function downloadBulk() {
  const urls = getBulkUrls();
  if (urls.length === 0) {
    setBulkMessage("Enter at least one URL.", "error");
    return;
  }
  if (urls.length > 20) {
    setBulkMessage("A maximum of 20 URLs can be submitted at once.", "error");
    return;
  }

  const duplicates = findDuplicates(urls);
  const uniqueUrls = [...new Set(urls)];
  bulkDownloadButton.disabled = true;
  bulkCheckButton.disabled = true;
  setBulkMessage(`Submitting ${uniqueUrls.length} unique URL(s)…`);

  try {
    const response = await requestJson("/api/bulk-download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: uniqueUrls }),
    });
    const queued = response.results.filter((item) => item.status === "queued");
    const rejected = response.results.filter((item) => item.status !== "queued");
    let finished = 0;

    setBulkMessage(
      `${queued.length} download(s) queued; ${rejected.length} could not be queued.` +
        (duplicates.size ? ` Skipped ${duplicates.size} duplicate URL(s).` : ""),
      rejected.length ? "error" : "success",
    );

    const outcomes = await Promise.allSettled(queued.map(async (item) => {
      await downloadJob(item.job_id, item.url, item.url, "video");
      finished += 1;
      setBulkMessage(`${finished} of ${queued.length} download(s) completed.`);
    }));
    const failed = outcomes.filter((outcome) => outcome.status === "rejected").length;
    const rejectedSummary = rejected.length
      ? ` Rejected: ${rejected.map((item) => `${item.url} (${item.error})`).join("; ")}.`
      : "";
    setBulkMessage(
      `${finished} of ${queued.length} download(s) completed; ${failed} download(s) failed.${rejectedSummary}`,
      failed || rejected.length ? "error" : "success",
    );
  } catch (error) {
    setBulkMessage(error.message, "error");
  } finally {
    bulkDownloadButton.disabled = false;
    bulkCheckButton.disabled = false;
  }
}

async function checkServiceStatus() {
  try {
    await requestJson("/api/health");
    serviceStatus.textContent = "Online";
    serviceStatus.dataset.state = "online";
  } catch {
    serviceStatus.textContent = "Offline";
    serviceStatus.dataset.state = "offline";
  }
}

analyzeButton.addEventListener("click", analyzeURL);
urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    analyzeURL();
  }
});
qualitySelect.addEventListener("change", () => {
  defaultFormatSelect.value = qualitySelect.value === "audio" ? "audio" : "video";
  saveSettings();
});
downloadButton.addEventListener("click", downloadCurrent);
bulkCheckButton.addEventListener("click", () => {
  const duplicates = findDuplicates(getBulkUrls());
  setBulkMessage(
    duplicates.size
      ? `Found ${duplicates.size} duplicate URL(s). They will be skipped when downloading.`
      : "No duplicate URLs found.",
    duplicates.size ? "error" : "success",
  );
});
bulkDownloadButton.addEventListener("click", downloadBulk);
clearHistoryButton.addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});
defaultFormatSelect.addEventListener("change", () => {
  qualitySelect.value = defaultFormatSelect.value === "audio" ? "audio" : "best";
  saveSettings();
});
themeSelect.addEventListener("change", () => {
  document.body.dataset.theme = themeSelect.value;
  saveSettings();
});

applySettings();
renderHistory();
checkServiceStatus();
