/**
 * SafeOps LogCollector - Webhook Routes
 * Handles incoming CI/CD webhooks from GitHub Actions and GitLab CI
 */

const express = require("express");
const { v4: uuidv4 } = require("uuid");
const { verifySignature } = require("../middleware/signature");
const rabbitmq = require("../services/rabbitmq");
const mongodb = require("../services/mongodb");
const { getGitHubService } = require("../services/github");
const { getGitLabService } = require("../services/gitlab");
const logger = require("../config/logger");

const router = express.Router();

/**
 * POST /webhook
 * Main webhook endpoint for CI/CD log ingestion
 */
router.post("/webhook", verifySignature, async (req, res) => {
  const startTime = Date.now();
  const requestId = uuidv4();

  try {
    const payload = req.body;
    const provider = req.provider;
    const signatureValid = req.signatureValid;

    // Extract build identifier based on provider
    let buildId;
    if (provider === "github") {
      buildId = payload.workflow_run?.id || payload.action;
    } else if (provider === "gitlab") {
      buildId = payload.object_attributes?.id || payload.object_kind;
    } else {
      buildId = payload.build_id || "unknown";
    }

    logger.info("Webhook received", {
      requestId,
      provider,
      buildId,
      signatureValid,
      contentLength: req.headers["content-length"],
    });

    // Try to fetch additional logs/metrics from provider API
    let enrichedMetrics = null;
    if (provider === "github" && payload.action === "completed") {
      const githubService = getGitHubService();
      enrichedMetrics = await githubService.processWorkflowRunEvent(payload);
    } else if (provider === "gitlab") {
      const gitlabService = getGitLabService();
      enrichedMetrics = await gitlabService.processPipelineEvent(payload);
    }

    // Store in MongoDB for audit trail
    const mongoId = await mongodb.storeRawLog(
      payload,
      provider,
      signatureValid
    );

    // Enrich payload with metadata and fetched metrics
    const enrichedPayload = {
      _meta: {
        request_id: requestId,
        mongo_id: mongoId,
        provider,
        signature_valid: signatureValid,
        received_at: new Date().toISOString(),
        source_ip: req.ip,
        logs_fetched: !!enrichedMetrics,
      },
      ...payload,
      // Merge in any fetched metrics
      ...(enrichedMetrics && { _enriched: enrichedMetrics }),
    };

    // Publish to RabbitMQ for processing
    const published = await rabbitmq.publish(enrichedPayload);

    const processingTime = Date.now() - startTime;

    logger.info("Webhook processed", {
      requestId,
      buildId,
      mongoStored: !!mongoId,
      queuePublished: published,
      logsFetched: !!enrichedMetrics,
      processingTimeMs: processingTime,
    });

    res.status(202).json({
      status: "accepted",
      request_id: requestId,
      build_id: buildId,
      stored: !!mongoId,
      queued: published,
      logs_fetched: !!enrichedMetrics,
      processing_time_ms: processingTime,
    });
  } catch (error) {
    logger.error("Webhook processing failed", {
      requestId,
      error: error.message,
      stack: error.stack,
    });

    res.status(500).json({
      status: "error",
      request_id: requestId,
      message: "Internal server error",
    });
  }
});

/**
 * POST /webhook/github
 * Explicit GitHub Actions endpoint
 */
router.post("/webhook/github", verifySignature, async (req, res) => {
  req.provider = "github";
  // Reuse main webhook handler logic
  const handler = router.stack.find((r) => r.route?.path === "/webhook");
  handler.route.stack[1].handle(req, res);
});

/**
 * POST /webhook/gitlab
 * Explicit GitLab CI endpoint
 */
router.post("/webhook/gitlab", verifySignature, async (req, res) => {
  req.provider = "gitlab";
  const handler = router.stack.find((r) => r.route?.path === "/webhook");
  handler.route.stack[1].handle(req, res);
});

/**
 * POST /webhook/test
 * Test endpoint for synthetic data injection (development only)
 * Now also fetches real logs from GitHub if workflow_run data is provided
 */
router.post("/webhook/test", async (req, res) => {
  const requestId = uuidv4();

  try {
    const payload = req.body;

    logger.info("Test webhook received", { requestId });

    // Try to fetch real logs if this looks like a GitHub workflow_run
    let enrichedMetrics = null;
    const githubService = getGitHubService();

    if (payload.action === "completed" && payload.workflow_run) {
      // Full webhook payload format
      enrichedMetrics = await githubService.processWorkflowRunEvent(payload);
    } else if (payload.repository && payload.run_id) {
      // Simple test format: { repository: "owner/repo", run_id: 123 }
      const repoStr = payload.repository; // Save the string before we overwrite
      const [owner, repo] = repoStr.split("/");

      // Create properly structured payload
      payload.action = "completed";
      payload.workflow_run = {
        id: payload.run_id,
        name: "Test Workflow",
        head_branch: "main",
        head_sha: "test-sha",
        status: "completed",
        conclusion: "success",
      };
      payload.repository = {
        full_name: repoStr,
        name: repo,
        owner: { login: owner },
      };

      // Fetch logs with the synthetic payload
      enrichedMetrics = await githubService.processWorkflowRunEvent(payload);
    }

    // Enrich payload
    const enrichedPayload = {
      _meta: {
        request_id: requestId,
        provider: "test",
        signature_valid: true,
        received_at: new Date().toISOString(),
        is_test: true,
        logs_fetched: !!enrichedMetrics,
      },
      ...payload,
      // Merge in any fetched metrics (including raw_logs)
      ...(enrichedMetrics && { _enriched: enrichedMetrics }),
    };

    // Store and publish
    const mongoId = await mongodb.storeRawLog(payload, "test", true);
    const published = await rabbitmq.publish(enrichedPayload);

    res.status(202).json({
      status: "accepted",
      request_id: requestId,
      stored: !!mongoId,
      queued: published,
      logs_fetched: !!enrichedMetrics,
    });
  } catch (error) {
    logger.error("Test webhook failed", { requestId, error: error.message });
    res.status(500).json({ status: "error", message: error.message });
  }
});

module.exports = router;
