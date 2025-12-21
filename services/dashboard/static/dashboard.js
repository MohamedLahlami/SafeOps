// SafeOps Dashboard JavaScript

const API_BASE = "";

// State
let allResults = [];
let showAnomaliesOnly = false;

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadStats();
  loadResults();

  // Event listeners
  document
    .getElementById("analyzeForm")
    .addEventListener("submit", handleAnalyze);
  document
    .getElementById("showAnomaliesOnly")
    .addEventListener("change", handleFilterChange);
  document.getElementById("refreshBtn").addEventListener("click", refreshData);

  // Auto-refresh every 30 seconds
  setInterval(refreshData, 30000);
});

// Check API Health
async function checkHealth() {
  const badge = document.getElementById("healthBadge");
  try {
    const response = await fetch(`${API_BASE}/api/health`);
    const data = await response.json();

    if (data.status === "healthy") {
      badge.textContent = "🟢 Model Healthy";
      badge.className = "status-badge status-healthy";
    } else {
      badge.textContent = "🟡 Model Loading";
      badge.className = "status-badge status-unknown";
    }
  } catch (error) {
    badge.textContent = "🔴 API Unavailable";
    badge.className = "status-badge status-unavailable";
  }
}

// Load Statistics
async function loadStats() {
  try {
    const response = await fetch(`${API_BASE}/api/stats`);
    const data = await response.json();

    document.getElementById("totalAnalyzed").textContent =
      data.total_analyzed || 0;
    document.getElementById("anomaliesDetected").textContent =
      data.anomalies_detected || 0;
    document.getElementById("normalBuilds").textContent =
      data.normal_builds || 0;

    const rate =
      data.total_analyzed > 0
        ? ((data.anomalies_detected / data.total_analyzed) * 100).toFixed(1)
        : "0.0";
    document.getElementById("detectionRate").textContent = `${rate}%`;
  } catch (error) {
    console.error("Failed to load stats:", error);
  }
}

// Load Results
async function loadResults() {
  const tableBody = document.getElementById("resultsBody");
  tableBody.innerHTML =
    '<tr class="loading"><td colspan="7">Loading results...</td></tr>';

  try {
    const response = await fetch(`${API_BASE}/api/results`);
    const data = await response.json();

    allResults = data.results || [];
    renderResults();
  } catch (error) {
    console.error("Failed to load results:", error);
    tableBody.innerHTML =
      '<tr class="loading"><td colspan="7">Failed to load results</td></tr>';
  }
}

// Render Results Table
function renderResults() {
  const tableBody = document.getElementById("resultsBody");

  let filtered = allResults;
  if (showAnomaliesOnly) {
    filtered = allResults.filter((r) => r.is_anomaly);
  }

  if (filtered.length === 0) {
    tableBody.innerHTML = `<tr class="loading"><td colspan="7">
            ${
              showAnomaliesOnly
                ? "No anomalies detected"
                : "No analysis results yet. Analyze a workflow to get started."
            }
        </td></tr>`;
    return;
  }

  tableBody.innerHTML = filtered
    .map(
      (result) => `
        <tr onclick="showDetails('${
          result.workflow_id
        }')" style="cursor: pointer;">
            <td>
                <strong>${result.workflow_id || result.id || "N/A"}</strong>
                ${
                  result.repo
                    ? `<br><small style="color: var(--text-secondary)">${result.repo}</small>`
                    : ""
                }
            </td>
            <td>${formatDate(result.timestamp || result.analyzed_at)}</td>
            <td>
                <span class="badge ${
                  result.is_anomaly ? "badge-anomaly" : "badge-normal"
                }">
                    ${result.is_anomaly ? "Anomaly" : "Normal"}
                </span>
            </td>
            <td class="score-cell ${
              result.anomaly_score < 0 ? "score-negative" : "score-positive"
            }">
                ${result.anomaly_score?.toFixed(4) || "N/A"}
            </td>
            <td>
                <div class="confidence-bar">
                    <div class="confidence-fill" style="width: ${
                      (result.confidence || 0.5) * 100
                    }%"></div>
                </div>
                ${((result.confidence || 0.5) * 100).toFixed(0)}%
            </td>
            <td>${renderReasons(result.reasons || result.anomaly_reasons)}</td>
            <td>${result.features?.suspicious_commands || 0}</td>
        </tr>
    `
    )
    .join("");
}

// Render Reasons Tags
function renderReasons(reasons) {
  if (!reasons || reasons.length === 0) {
    return '<span style="color: var(--text-secondary)">-</span>';
  }

  return (
    reasons
      .slice(0, 2)
      .map((reason) => {
        const isCritical =
          reason.toLowerCase().includes("suspicious") ||
          reason.toLowerCase().includes("encoded") ||
          reason.toLowerCase().includes("external");
        return `<span class="reason-tag ${
          isCritical ? "critical" : "warning"
        }">${truncate(reason, 20)}</span>`;
      })
      .join("") +
    (reasons.length > 2
      ? `<span class="reason-tag">+${reasons.length - 2}</span>`
      : "")
  );
}

// Handle Analyze Form
async function handleAnalyze(e) {
  e.preventDefault();

  const owner = document.getElementById("repoOwner").value.trim();
  const repo = document.getElementById("repoName").value.trim();
  const workflowId = document.getElementById("workflowId").value.trim();

  if (!owner || !repo || !workflowId) {
    showAnalyzeResult("Please fill in all fields", "error");
    return;
  }

  const btn = document.getElementById("analyzeBtn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analyzing...';

  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, repo, workflow_id: workflowId }),
    });

    const data = await response.json();

    if (data.error) {
      showAnalyzeResult(`Error: ${data.error}`, "error");
    } else {
      const resultType = data.is_anomaly ? "anomaly" : "success";
      const message = data.is_anomaly
        ? `⚠️ Anomaly Detected! Score: ${data.anomaly_score?.toFixed(4)}`
        : `✅ Normal build. Score: ${data.anomaly_score?.toFixed(4)}`;
      showAnalyzeResult(message, resultType);

      // Refresh data
      await refreshData();
    }
  } catch (error) {
    showAnalyzeResult(`Failed to analyze: ${error.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// Show Analyze Result
function showAnalyzeResult(message, type) {
  const resultDiv = document.getElementById("analyzeResult");
  resultDiv.textContent = message;
  resultDiv.className = `analyze-result ${type}`;
  resultDiv.classList.remove("hidden");

  // Auto-hide after 10 seconds
  setTimeout(() => {
    resultDiv.classList.add("hidden");
  }, 10000);
}

// Show Details Modal
function showDetails(workflowId) {
  const result = allResults.find((r) => (r.workflow_id || r.id) === workflowId);
  if (!result) return;

  const modal = document.getElementById("detailModal");
  const modalBody = modal.querySelector(".modal-body");

  const features = result.features || {};
  const reasons = result.reasons || result.anomaly_reasons || [];

  modalBody.innerHTML = `
        <h3>Analysis Summary</h3>
        <div style="margin: 1rem 0; padding: 1rem; background: var(--bg-tertiary); border-radius: 8px;">
            <p><strong>Workflow ID:</strong> ${
              result.workflow_id || result.id
            }</p>
            ${
              result.repo
                ? `<p><strong>Repository:</strong> ${result.repo}</p>`
                : ""
            }
            <p><strong>Status:</strong> 
                <span class="badge ${
                  result.is_anomaly ? "badge-anomaly" : "badge-normal"
                }">
                    ${result.is_anomaly ? "Anomaly" : "Normal"}
                </span>
            </p>
            <p><strong>Anomaly Score:</strong> 
                <span class="${
                  result.anomaly_score < 0 ? "score-negative" : "score-positive"
                }">
                    ${result.anomaly_score?.toFixed(6) || "N/A"}
                </span>
            </p>
            <p><strong>Analyzed:</strong> ${formatDate(
              result.timestamp || result.analyzed_at
            )}</p>
        </div>
        
        ${
          reasons.length > 0
            ? `
        <h3>Detection Reasons</h3>
        <ul class="reason-list">
            ${reasons
              .map(
                (r) => `
                <li>
                    <span class="icon">⚠️</span>
                    <span>${r}</span>
                </li>
            `
              )
              .join("")}
        </ul>
        `
            : ""
        }
        
        <h3>Extracted Features</h3>
        <div class="feature-grid">
            ${renderFeatureItem(
              "Suspicious Commands",
              features.suspicious_commands,
              features.suspicious_commands > 0
            )}
            ${renderFeatureItem(
              "External URLs",
              features.external_urls_count || features.external_url_count,
              features.external_urls_count > 5
            )}
            ${renderFeatureItem(
              "Base64 Patterns",
              features.base64_patterns,
              features.base64_patterns > 0
            )}
            ${renderFeatureItem(
              "External IPs",
              features.external_ip_count || features.unique_ips_contacted,
              features.external_ip_count > 0
            )}
            ${renderFeatureItem(
              "Env Variables",
              features.env_var_usage,
              features.env_var_usage > 20
            )}
            ${renderFeatureItem("Total Lines", features.total_lines, false)}
            ${renderFeatureItem(
              "Char Density",
              features.char_density?.toFixed(2),
              features.char_density > 100
            )}
            ${renderFeatureItem(
              "Error Count",
              features.error_count,
              features.error_count > 10
            )}
            ${renderFeatureItem(
              "Unique Templates",
              features.unique_templates,
              false
            )}
            ${renderFeatureItem(
              "Template Entropy",
              features.template_entropy?.toFixed(3),
              false
            )}
        </div>
    `;

  modal.classList.remove("hidden");

  // Close on backdrop click
  modal.onclick = (e) => {
    if (e.target === modal) closeModal();
  };
}

// Render Feature Item
function renderFeatureItem(label, value, highlight) {
  if (value === undefined || value === null) return "";
  return `
        <div class="feature-item">
            <label>${label}</label>
            <div class="value ${highlight ? "highlight" : ""}">${value}</div>
        </div>
    `;
}

// Close Modal
function closeModal() {
  document.getElementById("detailModal").classList.add("hidden");
}

// Handle Filter Change
function handleFilterChange(e) {
  showAnomaliesOnly = e.target.checked;
  renderResults();
}

// Refresh Data
async function refreshData() {
  await Promise.all([loadStats(), loadResults()]);
  checkHealth();
}

// Format Date
function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  const date = new Date(dateStr);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Truncate String
function truncate(str, len) {
  if (!str) return "";
  return str.length > len ? str.substring(0, len) + "..." : str;
}

// Keyboard shortcuts
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
  }
});
