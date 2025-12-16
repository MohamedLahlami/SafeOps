/**
 * SafeOps LogCollector - Health & Status Routes
 */

const express = require("express");
const rabbitmq = require("../services/rabbitmq");
const mongodb = require("../services/mongodb");

const router = express.Router();

/**
 * GET /health
 * Basic health check
 */
router.get("/health", (req, res) => {
  res.json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    service: "log-collector",
  });
});

/**
 * GET /health/ready
 * Readiness check - verifies all dependencies are connected
 */
router.get("/health/ready", async (req, res) => {
  const rabbitStatus = rabbitmq.getStatus();
  const mongoStatus = mongodb.getStatus();

  const isReady = rabbitStatus.connected && mongoStatus.connected;

  res.status(isReady ? 200 : 503).json({
    status: isReady ? "ready" : "not_ready",
    timestamp: new Date().toISOString(),
    dependencies: {
      rabbitmq: rabbitStatus,
      mongodb: mongoStatus,
    },
  });
});

/**
 * GET /stats
 * Service statistics
 */
router.get("/stats", async (req, res) => {
  try {
    const mongoStats = await mongodb.getStats();
    const rabbitStatus = rabbitmq.getStatus();

    res.json({
      timestamp: new Date().toISOString(),
      logs: mongoStats,
      queue: rabbitStatus,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
