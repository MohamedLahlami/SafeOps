/**
 * SafeOps LogCollector - GitHub Integration Service
 *
 * Fetches actual workflow logs from GitHub Actions API.
 * Requires GITHUB_TOKEN environment variable with 'actions:read' scope.
 */

const https = require("https");
const zlib = require("zlib");
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
              else resolve({ data: unzipped.toString(), headers: res.headers });
            });
          } else if (options.raw) {
            resolve({ data: body, headers: res.headers });
          } else {
            try {
              resolve({
                data: JSON.parse(body.toString()),
                headers: res.headers,
              });
            } catch (e) {
              resolve({ data: body.toString(), headers: res.headers });
            }
          }
        });
      });

      req.on("error", reject);
      req.end();
    });
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
   * Download workflow run logs (zip archive)
   */
  async downloadRunLogs(owner, repo, runId) {
    if (!this.enabled) {
      logger.warn("GitHub integration not enabled");
      return null;
    }

    try {
      // Get the logs download URL
      const { headers } = await this._request(
        `/repos/${owner}/${repo}/actions/runs/${runId}/logs`,
        { raw: true }
      );

      // GitHub returns a redirect to the actual download URL
      if (headers.location) {
        logger.info("Following redirect for logs download", {
          owner,
          repo,
          runId,
        });
        // Note: For actual implementation, would need to follow the redirect
        // and unzip the archive. For now, return metadata.
        return {
          download_url: headers.location,
          message: "Logs available for download",
        };
      }

      return null;
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
  extractMetrics(workflowRun, jobs) {
    const startTime = new Date(
      workflowRun.run_started_at || workflowRun.created_at
    );
    const endTime = new Date(workflowRun.updated_at);
    const durationSeconds = Math.floor((endTime - startTime) / 1000);

    // Count job steps
    let totalSteps = 0;
    let completedSteps = 0;
    let failedSteps = 0;

    for (const job of jobs) {
      if (job.steps) {
        totalSteps += job.steps.length;
        completedSteps += job.steps.filter(
          (s) => s.status === "completed"
        ).length;
        failedSteps += job.steps.filter(
          (s) => s.conclusion === "failure"
        ).length;
      }
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
      metrics: {
        duration_seconds: durationSeconds,
        step_count: totalSteps,
        completed_steps: completedSteps,
        failed_steps: failedSteps,
        job_count: jobs.length,
        // Will be populated after log parsing
        log_line_count: 0,
        char_density: 0,
        error_count: failedSteps,
        warning_count: 0,
      },
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

    const owner = payload.repository?.owner?.login;
    const repo = payload.repository?.name;
    const runId = workflowRun.id;

    logger.info("Processing completed workflow run", { owner, repo, runId });

    try {
      // Get job details
      const jobs = await this.getWorkflowJobs(owner, repo, runId);

      // Extract metrics
      const metrics = this.extractMetrics(workflowRun, jobs);

      // Try to get logs info
      const logsInfo = await this.downloadRunLogs(owner, repo, runId);
      if (logsInfo) {
        metrics.logs_url = logsInfo.download_url;
      }

      logger.info("Extracted workflow metrics", {
        runId,
        duration: metrics.duration_seconds,
        steps: metrics.metrics.step_count,
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
