/**
 * SafeOps LogCollector - GitHub Integration Service
 *
 * Fetches actual workflow logs from GitHub Actions API.
 * Requires GITHUB_TOKEN environment variable with 'actions:read' scope.
 */

const https = require("https");
const AdmZip = require("adm-zip");
const { URL } = require("url");
const logger = require("../config/logger");
const config = require("../config");

class GitHubService {
  constructor() {
    this.token = config.github.token;
    this.baseUrl = "api.github.com";
    this.enabled = !!this.token;

    if (this.enabled) {
      logger.info("GitHub integration enabled");
    } else {
      logger.warn(
        "GitHub integration disabled - set GITHUB_TOKEN to enable log fetching"
      );
    }
  }

  /**
   * Make authenticated request to GitHub API
   */
  async _request(path, options = {}) {
    return new Promise((resolve, reject) => {
      const reqOptions = {
        hostname: this.baseUrl,
        path,
        method: options.method || "GET",
        headers: {
          Authorization: `Bearer ${this.token}`,
          Accept: options.accept || "application/vnd.github+json",
          "User-Agent": "SafeOps-LogMiner/1.0",
          "X-GitHub-Api-Version": "2022-11-28",
        },
      };

      const req = https.request(reqOptions, (res) => {
        // Handle redirects - return the location for the caller to follow
        if (res.statusCode === 302 || res.statusCode === 301) {
          resolve({
            data: null,
            headers: res.headers,
            statusCode: res.statusCode,
            redirect: res.headers.location,
          });
          return;
        }

        const chunks = [];

        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const body = Buffer.concat(chunks);

          if (res.statusCode >= 400) {
            reject(
              new Error(
                `GitHub API error: ${res.statusCode} - ${body.toString()}`
              )
            );
            return;
          }

          // Handle compressed responses
          if (res.headers["content-encoding"] === "gzip") {
            zlib.gunzip(body, (err, unzipped) => {
              if (err) reject(err);
              else
                resolve({
                  data: unzipped.toString(),
                  headers: res.headers,
                  statusCode: res.statusCode,
                });
            });
          } else if (options.raw) {
            resolve({
              data: body,
              headers: res.headers,
              statusCode: res.statusCode,
            });
          } else {
            try {
              resolve({
                data: JSON.parse(body.toString()),
                headers: res.headers,
                statusCode: res.statusCode,
              });
            } catch (e) {
              resolve({
                data: body.toString(),
                headers: res.headers,
                statusCode: res.statusCode,
              });
            }
          }
        });
      });

      req.on("error", reject);
      req.end();
    });
  }

  /**
   * Download content from a URL (follows redirects)
   */
  async _downloadUrl(urlString, maxRedirects = 5) {
    return new Promise((resolve, reject) => {
      if (maxRedirects <= 0) {
        reject(new Error("Too many redirects"));
        return;
      }

      const parsedUrl = new URL(urlString);
      const protocol =
        parsedUrl.protocol === "https:" ? https : require("http");

      const reqOptions = {
        hostname: parsedUrl.hostname,
        path: parsedUrl.pathname + parsedUrl.search,
        method: "GET",
        headers: {
          "User-Agent": "SafeOps-LogMiner/1.0",
          Accept: "*/*",
        },
      };

      const req = protocol.request(reqOptions, (res) => {
        // Handle redirects
        if (res.statusCode === 302 || res.statusCode === 301) {
          this._downloadUrl(res.headers.location, maxRedirects - 1)
            .then(resolve)
            .catch(reject);
          return;
        }

        if (res.statusCode >= 400) {
          reject(new Error(`Download failed: ${res.statusCode}`));
          return;
        }

        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          resolve(Buffer.concat(chunks));
        });
      });

      req.on("error", reject);
      req.end();
    });
  }

  /**
   * Extract text from a zip buffer containing log files
   * GitHub returns workflow logs as a zip archive with .txt files
   * Uses adm-zip library to handle all zip formats including data descriptors
   */
  _extractLogsFromZip(zipBuffer) {
    try {
      const zip = new AdmZip(zipBuffer);
      const entries = zip.getEntries();
      const allLogs = [];

      for (const entry of entries) {
        const fileName = entry.entryName;

        // Only process .txt log files (skip directories)
        if (fileName.endsWith(".txt") && !entry.isDirectory) {
          try {
            const content = entry.getData().toString("utf8");

            if (content) {
              allLogs.push({
                fileName,
                content,
                lines: content.split("\n").length,
              });

              logger.debug(
                `Extracted log file: ${fileName} (${content.length} chars)`
              );
            }
          } catch (extractErr) {
            logger.warn(`Failed to extract ${fileName}: ${extractErr.message}`);
          }
        }
      }

      return allLogs;
    } catch (error) {
      logger.error(`Failed to parse zip archive: ${error.message}`);
      return [];
    }
  }

  /**
   * Get workflow run details
   */
  async getWorkflowRun(owner, repo, runId) {
    if (!this.enabled) {
      logger.warn("GitHub integration not enabled");
      return null;
    }

    try {
      const { data } = await this._request(
        `/repos/${owner}/${repo}/actions/runs/${runId}`
      );
      return data;
    } catch (error) {
      logger.error("Failed to get workflow run", {
        owner,
        repo,
        runId,
        error: error.message,
      });
      return null;
    }
  }

  /**
   * Get workflow run jobs
   */
  async getWorkflowJobs(owner, repo, runId) {
    if (!this.enabled) return [];

    try {
      const { data } = await this._request(
        `/repos/${owner}/${repo}/actions/runs/${runId}/jobs`
      );
      return data.jobs || [];
    } catch (error) {
      logger.error("Failed to get workflow jobs", {
        owner,
        repo,
        runId,
        error: error.message,
      });
      return [];
    }
  }

  /**
   * Download and extract workflow run logs
   * Returns the actual log content as a string
   */
  async downloadRunLogs(owner, repo, runId) {
    if (!this.enabled) {
      logger.warn("GitHub integration not enabled");
      return null;
    }

    try {
      // Get the logs download URL (GitHub returns a 302 redirect)
      const { redirect } = await this._request(
        `/repos/${owner}/${repo}/actions/runs/${runId}/logs`,
        { raw: true }
      );

      if (!redirect) {
        logger.warn("No redirect URL for logs download", {
          owner,
          repo,
          runId,
        });
        return null;
      }

      logger.info("Downloading logs archive", { owner, repo, runId });

      // Download the zip file
      const zipBuffer = await this._downloadUrl(redirect);

      logger.info("Downloaded logs archive", {
        owner,
        repo,
        runId,
        sizeBytes: zipBuffer.length,
      });

      // Extract log files from zip (synchronous with adm-zip)
      const logFiles = this._extractLogsFromZip(zipBuffer);

      const totalLines = logFiles.reduce((sum, f) => sum + f.lines, 0);

      logger.info("Extracted log files", {
        owner,
        repo,
        runId,
        fileCount: logFiles.length,
        totalLines,
      });

      // Combine all log content
      const combinedLogs = logFiles
        .map((f) => `=== ${f.fileName} ===\n${f.content}`)
        .join("\n\n");

      return {
        raw_logs: combinedLogs,
        file_count: logFiles.length,
        total_lines: totalLines,
        files: logFiles.map((f) => ({ name: f.fileName, lines: f.lines })),
      };
    } catch (error) {
      logger.error("Failed to download run logs", {
        owner,
        repo,
        runId,
        error: error.message,
      });
      return null;
    }
  }

  /**
   * Extract build metrics from workflow run
   */
  extractMetrics(workflowRun, jobs, logsData = null) {
    // Parse dates with fallbacks
    const startTimeStr = workflowRun.run_started_at || workflowRun.created_at;
    const endTimeStr = workflowRun.updated_at || workflowRun.run_started_at;

    let startTime, endTime, durationSeconds;

    if (startTimeStr) {
      startTime = new Date(startTimeStr);
      endTime = endTimeStr ? new Date(endTimeStr) : new Date();
      durationSeconds = Math.max(0, Math.floor((endTime - startTime) / 1000));
    } else {
      // Fallback to current time if no timestamps available
      startTime = new Date();
      endTime = new Date();
      durationSeconds = 0;
    }

    // Count job steps
    let totalSteps = 0;
    let completedSteps = 0;
    let failedSteps = 0;
    const stepDetails = [];

    for (const job of jobs) {
      if (job.steps) {
        totalSteps += job.steps.length;
        completedSteps += job.steps.filter(
          (s) => s.status === "completed"
        ).length;
        failedSteps += job.steps.filter(
          (s) => s.conclusion === "failure"
        ).length;

        // Collect step details for log-parser
        for (const step of job.steps) {
          stepDetails.push({
            name: step.name,
            status: step.status,
            conclusion: step.conclusion,
            number: step.number,
          });
        }
      }
    }

    // Calculate log metrics from actual logs if available
    let logLineCount = 0;
    let charDensity = 0;
    let errorCount = failedSteps;
    let warningCount = 0;
    let rawLogs = "";

    if (logsData && logsData.raw_logs) {
      rawLogs = logsData.raw_logs;
      const lines = rawLogs.split("\n");
      logLineCount = lines.length;

      // Calculate character density (average chars per line)
      const totalChars = rawLogs.length;
      charDensity = logLineCount > 0 ? totalChars / logLineCount : 0;

      // Count errors and warnings in log content
      const errorPatterns =
        /\b(error|failed|failure|exception|fatal|critical)\b/gi;
      const warningPatterns = /\b(warning|warn|deprecated|caution)\b/gi;

      const errorMatches = rawLogs.match(errorPatterns);
      const warningMatches = rawLogs.match(warningPatterns);

      errorCount = errorMatches ? errorMatches.length : 0;
      warningCount = warningMatches ? warningMatches.length : 0;
    }

    return {
      build_id: `github-${workflowRun.id}`,
      repository: workflowRun.repository?.full_name || "unknown",
      branch: workflowRun.head_branch,
      commit_sha: workflowRun.head_sha,
      status: workflowRun.status,
      conclusion: workflowRun.conclusion,
      workflow_name: workflowRun.name,
      started_at: startTime.toISOString(),
      completed_at: endTime.toISOString(),
      duration_seconds: durationSeconds,
      // Raw logs for the log-parser
      raw_logs: rawLogs,
      // Pre-calculated metrics (log-parser can override these)
      metrics: {
        duration_seconds: durationSeconds,
        step_count: totalSteps,
        completed_steps: completedSteps,
        failed_steps: failedSteps,
        job_count: jobs.length,
        log_line_count: logLineCount,
        char_density: Math.round(charDensity * 100) / 100,
        error_count: errorCount,
        warning_count: warningCount,
      },
      steps: stepDetails,
      log_files: logsData?.files || [],
    };
  }

  /**
   * Process a workflow_run webhook event
   */
  async processWorkflowRunEvent(payload) {
    if (!this.enabled) {
      logger.info("GitHub integration disabled, using webhook payload only");
      return null;
    }

    const workflowRun = payload.workflow_run;
    if (!workflowRun) {
      logger.warn("No workflow_run in payload");
      return null;
    }

    // Only process completed runs
    if (workflowRun.status !== "completed") {
      logger.info("Workflow not yet completed, skipping log fetch", {
        runId: workflowRun.id,
        status: workflowRun.status,
      });
      return null;
    }

    // Extract owner and repo - handle both full payloads and simplified ones
    let owner, repo;
    if (payload.repository?.owner?.login) {
      owner = payload.repository.owner.login;
      repo = payload.repository.name;
    } else if (payload.repository?.full_name) {
      // Handle simplified payload with just full_name
      const parts = payload.repository.full_name.split("/");
      owner = parts[0];
      repo = parts[1];
    } else {
      logger.warn("Cannot determine repository owner/name from payload");
      return null;
    }

    const runId = workflowRun.id;

    logger.info("Processing completed workflow run", { owner, repo, runId });

    try {
      // Get job details
      const jobs = await this.getWorkflowJobs(owner, repo, runId);

      // Download and extract actual logs
      const logsData = await this.downloadRunLogs(owner, repo, runId);

      // Extract metrics with actual log content
      const metrics = this.extractMetrics(workflowRun, jobs, logsData);

      logger.info("Extracted workflow metrics", {
        runId,
        duration: metrics.duration_seconds,
        steps: metrics.metrics.step_count,
        logLines: metrics.metrics.log_line_count,
        errors: metrics.metrics.error_count,
        warnings: metrics.metrics.warning_count,
      });

      return metrics;
    } catch (error) {
      logger.error("Failed to process workflow run", {
        owner,
        repo,
        runId,
        error: error.message,
      });
      return null;
    }
  }
}

// Singleton instance
let instance = null;

function getGitHubService() {
  if (!instance) {
    instance = new GitHubService();
  }
  return instance;
}

module.exports = { GitHubService, getGitHubService };
