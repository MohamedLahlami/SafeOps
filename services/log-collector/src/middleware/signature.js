/**
 * SafeOps LogCollector - HMAC Signature Verification Middleware
 * Validates webhook signatures from GitHub and GitLab
 */

const crypto = require("crypto");
const config = require("../config");
const logger = require("../config/logger");

/**
 * Verify webhook signature
 * Supports GitHub (sha256) and GitLab (token) authentication
 */
function verifySignature(req, res, next) {
  const payload = JSON.stringify(req.body);

  // Get signature from headers
  const githubSignature = req.headers["x-hub-signature-256"];
  const gitlabToken = req.headers["x-gitlab-token"];

  // Determine provider and validate
  if (githubSignature) {
    // GitHub HMAC-SHA256 signature
    const expectedSignature =
      "sha256=" +
      crypto
        .createHmac("sha256", config.webhookSecret)
        .update(payload)
        .digest("hex");

    const valid = crypto.timingSafeEqual(
      Buffer.from(githubSignature),
      Buffer.from(expectedSignature)
    );

    req.signatureValid = valid;
    req.provider = "github";

    if (!valid) {
      logger.warn("Invalid GitHub webhook signature", {
        ip: req.ip,
        path: req.path,
      });
    }
  } else if (gitlabToken) {
    // GitLab secret token
    req.signatureValid = gitlabToken === config.webhookSecret;
    req.provider = "gitlab";

    if (!req.signatureValid) {
      logger.warn("Invalid GitLab webhook token", {
        ip: req.ip,
        path: req.path,
      });
    }
  } else {
    // No signature provided - mark but allow (for testing)
    req.signatureValid = false;
    req.provider = "unknown";

    // In development, allow unsigned requests
    if (config.nodeEnv === "development") {
      logger.debug("No signature provided (development mode)", { ip: req.ip });
      req.signatureValid = true; // Allow for testing
    } else {
      logger.warn("No webhook signature provided", { ip: req.ip });
    }
  }

  // Attach signature status to request for logging
  req.signatureStatus = req.signatureValid ? "valid" : "invalid";

  next();
}

/**
 * Require valid signature (strict mode)
 * Use this middleware to reject invalid signatures
 */
function requireValidSignature(req, res, next) {
  if (!req.signatureValid && config.nodeEnv === "production") {
    return res.status(401).json({
      error: "Unauthorized",
      message: "Invalid webhook signature",
    });
  }
  next();
}

module.exports = {
  verifySignature,
  requireValidSignature,
};
