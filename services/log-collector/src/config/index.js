/**
 * SafeOps LogCollector - Configuration
 */

require("dotenv").config();

module.exports = {
  // Server
  port: parseInt(process.env.PORT, 10) || 3001,
  nodeEnv: process.env.NODE_ENV || "development",

  // MongoDB
  mongodb: {
    uri:
      process.env.MONGODB_URI ||
      "mongodb://admin:safeops123@localhost:27017/safeops?authSource=admin",
    options: {
      maxPoolSize: 10,
      serverSelectionTimeoutMS: 5000,
      socketTimeoutMS: 45000,
    },
  },

  // RabbitMQ
  rabbitmq: {
    url: process.env.RABBITMQ_URL || "amqp://safeops:safeops123@localhost:5672",
    queue: process.env.RABBITMQ_QUEUE || "raw_logs",
    options: {
      durable: true,
      persistent: true,
    },
  },

  // Security
  webhookSecret: process.env.WEBHOOK_SECRET || "dev-secret-key",

  // GitHub Integration
  github: {
    token: process.env.GITHUB_TOKEN || "",
    // Enable automatic log fetching when token is provided
    fetchLogs: !!process.env.GITHUB_TOKEN,
  },

  // GitLab Integration
  gitlab: {
    token: process.env.GITLAB_TOKEN || "",
    url: process.env.GITLAB_URL || "gitlab.com",
    // Enable automatic log fetching when token is provided
    fetchLogs: !!process.env.GITLAB_TOKEN,
  },

  // Rate Limiting
  rateLimit: {
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW_MS, 10) || 60000,
    max: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS, 10) || 100,
  },

  // Logging
  logLevel: process.env.LOG_LEVEL || "info",
};
