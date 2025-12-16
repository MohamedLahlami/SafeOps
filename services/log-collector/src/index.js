/**
 * SafeOps LogCollector - Entry Point
 * Starts the webhook ingestion service
 */

const app = require("./app");
const config = require("./config");
const logger = require("./config/logger");
const rabbitmq = require("./services/rabbitmq");
const mongodb = require("./services/mongodb");

async function start() {
  logger.info("Starting LogCollector service...", {
    nodeEnv: config.nodeEnv,
    port: config.port,
  });

  // Connect to services
  await Promise.all([mongodb.connect(), rabbitmq.connect()]);

  // Start HTTP server
  const server = app.listen(config.port, () => {
    logger.info(`LogCollector listening on port ${config.port}`);
    logger.info("Endpoints:");
    logger.info(`  POST /webhook       - Main webhook endpoint`);
    logger.info(`  POST /webhook/test  - Test endpoint`);
    logger.info(`  GET  /health        - Health check`);
    logger.info(`  GET  /health/ready  - Readiness check`);
    logger.info(`  GET  /stats         - Service statistics`);
  });

  // Graceful shutdown
  const shutdown = async (signal) => {
    logger.info(`${signal} received, shutting down gracefully...`);

    server.close(async () => {
      logger.info("HTTP server closed");

      await Promise.all([mongodb.close(), rabbitmq.close()]);

      logger.info("All connections closed");
      process.exit(0);
    });

    // Force exit if graceful shutdown takes too long
    setTimeout(() => {
      logger.error("Forced shutdown after timeout");
      process.exit(1);
    }, 10000);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

start().catch((error) => {
  logger.error("Failed to start LogCollector", { error: error.message });
  process.exit(1);
});
