/**
 * SafeOps LogCollector - Webhook Routes
 * Handles incoming CI/CD webhooks from GitHub Actions and GitLab CI
 */

const express = require("express");
const { v4: uuidv4 } = require("uuid");
const { verifySignature } = require("../middleware/signature");
const rabbitmq = require("../services/rabbitmq");
const mongodb = require("../services/mongodb");
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

    // Store in MongoDB for audit trail
    const mongoId = await mongodb.storeRawLog(
      payload,
      provider,
      signatureValid
    );

    // Enrich payload with metadata
    const enrichedPayload = {
      _meta: {
        request_id: requestId,
        mongo_id: mongoId,
        provider,
        signature_valid: signatureValid,
        received_at: new Date().toISOString(),
        source_ip: req.ip,
      },
      ...payload,
    };

    // Publish to RabbitMQ for processing
    const published = await rabbitmq.publish(enrichedPayload);

    const processingTime = Date.now() - startTime;

    logger.info("Webhook processed", {
      requestId,
      buildId,
      mongoStored: !!mongoId,
      queuePublished: published,
      processingTimeMs: processingTime,
    });

    res.status(202).json({
      status: "accepted",
      request_id: requestId,
      build_id: buildId,
      stored: !!mongoId,
      queued: published,
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
 */
router.post("/webhook/test", async (req, res) => {
  const requestId = uuidv4();

  try {
    const payload = req.body;

    logger.info("Test webhook received", { requestId });

    // Enrich payload
    const enrichedPayload = {
      _meta: {
        request_id: requestId,
        provider: "test",
        signature_valid: true,
        received_at: new Date().toISOString(),
        is_test: true,
      },
      ...payload,
    };

    // Store and publish
    const mongoId = await mongodb.storeRawLog(payload, "test", true);
    const published = await rabbitmq.publish(enrichedPayload);

    res.status(202).json({
      status: "accepted",
      request_id: requestId,
      stored: !!mongoId,
      queued: published,
    });
  } catch (error) {
    logger.error("Test webhook failed", { requestId, error: error.message });
    res.status(500).json({ status: "error", message: error.message });
  }
});

module.exports = router;
