/**
 * SafeOps LogCollector - GitLab Integration Service
 *
 * Fetches actual job logs from GitLab CI API.
 * Requires GITLAB_TOKEN environment variable with 'read_api' scope.
 */

const https = require("https");
const logger = require("../config/logger");
const config = require("../config");

class GitLabService {
  constructor() {
    this.token = config.gitlab.token;
    this.baseUrl = config.gitlab.url || "gitlab.com";
    this.enabled = !!this.token;

    if (this.enabled) {
      logger.info("GitLab integration enabled", { baseUrl: this.baseUrl });
    } else {
      logger.warn(
        "GitLab integration disabled - set GITLAB_TOKEN to enable log fetching"
      );
    }
  }

  /**
   * Make authenticated request to GitLab API
   */
  async _request(path, options = {}) {
    return new Promise((resolve, reject) => {
      const reqOptions = {
        hostname: this.baseUrl,
        path: `/api/v4${path}`,
        method: options.method || "GET",
        headers: {
          "PRIVATE-TOKEN": this.token,
          "Content-Type": "application/json",
          "User-Agent": "SafeOps-LogMiner/1.0",
        },
      };

      const req = https.request(reqOptions, (res) => {
        const chunks = [];

        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString();

          if (res.statusCode >= 400) {
            reject(new Error(`GitLab API error: ${res.statusCode} - ${body}`));
            return;
          }

          try {
            resolve({ data: JSON.parse(body), headers: res.headers });
          } catch (e) {
            resolve({ data: body, headers: res.headers });
          }
        });
      });

      req.on("error", reject);
      req.end();
    });
  }

  /**
   * Get pipeline details
   */
  async getPipeline(projectId, pipelineId) {
    if (!this.enabled) return null;

    try {
      const encodedProjectId = encodeURIComponent(projectId);
      const { data } = await this._request(
        `/projects/${encodedProjectId}/pipelines/${pipelineId}`
      );
      return data;
    } catch (error) {
      logger.error("Failed to get pipeline", {
        projectId,
        pipelineId,
        error: error.message,
      });
      return null;
    }
  }

  /**
   * Get pipeline jobs
   */
  async getPipelineJobs(projectId, pipelineId) {
    if (!this.enabled) return [];

    try {
      const encodedProjectId = encodeURIComponent(projectId);
      const { data } = await this._request(
        `/projects/${encodedProjectId}/pipelines/${pipelineId}/jobs`
      );
      return data || [];
    } catch (error) {
      logger.error("Failed to get pipeline jobs", {
        projectId,
        pipelineId,
        error: error.message,
      });
      return [];
    }
  }

  /**
   * Get job trace (logs)
   */
  async getJobTrace(projectId, jobId) {
    if (!this.enabled) return null;

    try {
      const encodedProjectId = encodeURIComponent(projectId);
      const { data } = await this._request(
        `/projects/${encodedProjectId}/jobs/${jobId}/trace`
      );
      return data; // Returns plain text log
    } catch (error) {
      logger.error("Failed to get job trace", {
        projectId,
        jobId,
        error: error.message,
      });
      return null;
    }
  }

  /**
   * Extract build metrics from pipeline
   */
  extractMetrics(pipeline, jobs, logs = "") {
    const startTime = new Date(pipeline.created_at);
    const endTime = new Date(pipeline.updated_at);
    const durationSeconds =
      pipeline.duration || Math.floor((endTime - startTime) / 1000);

    // Analyze logs
    const logLines = logs.split("\n");
    const errorCount = logLines.filter((l) =>
      /error|failed|exception/i.test(l)
    ).length;
    const warningCount = logLines.filter((l) => /warning|warn/i.test(l)).length;

    return {
      build_id: `gitlab-${pipeline.id}`,
      repository: pipeline.project_id,
      branch: pipeline.ref,
      commit_sha: pipeline.sha,
      status: pipeline.status,
      started_at: startTime.toISOString(),
      completed_at: endTime.toISOString(),
      duration_seconds: durationSeconds,
      log_content: logs,
      metrics: {
        duration_seconds: durationSeconds,
        log_line_count: logLines.length,
        char_density: logs.length / Math.max(logLines.length, 1),
        error_count: errorCount,
        warning_count: warningCount,
        step_count: jobs.length,
        job_count: jobs.length,
      },
    };
  }

  /**
   * Process a pipeline webhook event
   */
  async processPipelineEvent(payload) {
    if (!this.enabled) {
      logger.info("GitLab integration disabled, using webhook payload only");
      return null;
    }

    const pipeline = payload.object_attributes;
    if (!pipeline) {
      logger.warn("No object_attributes in payload");
      return null;
    }

    // Only process completed pipelines
    if (!["success", "failed", "canceled"].includes(pipeline.status)) {
      logger.info("Pipeline not yet completed, skipping log fetch", {
        pipelineId: pipeline.id,
        status: pipeline.status,
      });
      return null;
    }

    const projectId = payload.project?.id;
    const pipelineId = pipeline.id;

    logger.info("Processing completed pipeline", { projectId, pipelineId });

    try {
      // Get job details
      const jobs = await this.getPipelineJobs(projectId, pipelineId);

      // Get logs from all jobs
      let allLogs = "";
      for (const job of jobs) {
        const trace = await this.getJobTrace(projectId, job.id);
        if (trace) {
          allLogs += `\n=== Job: ${job.name} ===\n${trace}`;
        }
      }

      // Extract metrics
      const metrics = this.extractMetrics(pipeline, jobs, allLogs);

      logger.info("Extracted pipeline metrics", {
        pipelineId,
        duration: metrics.duration_seconds,
        jobs: jobs.length,
        logLines: metrics.metrics.log_line_count,
      });

      return metrics;
    } catch (error) {
      logger.error("Failed to process pipeline", {
        projectId,
        pipelineId,
        error: error.message,
      });
      return null;
    }
  }
}

// Singleton instance
let instance = null;

function getGitLabService() {
  if (!instance) {
    instance = new GitLabService();
  }
  return instance;
}

module.exports = { GitLabService, getGitLabService };
