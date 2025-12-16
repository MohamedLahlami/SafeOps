/**
 * SafeOps LogCollector - MongoDB Service
 * Stores raw webhook payloads for audit and reprocessing
 */

const { MongoClient, ObjectId } = require("mongodb");
const config = require("../config");
const logger = require("../config/logger");

class MongoDBService {
  constructor() {
    this.client = null;
    this.db = null;
    this.isConnected = false;
  }

  /**
   * Connect to MongoDB
   */
  async connect() {
    try {
      logger.info("Connecting to MongoDB...", {
        uri: config.mongodb.uri.replace(/:[^:@]+@/, ":***@"),
      });

      this.client = new MongoClient(config.mongodb.uri, config.mongodb.options);
      await this.client.connect();

      this.db = this.client.db();
      this.isConnected = true;

      logger.info("MongoDB connected successfully", {
        database: this.db.databaseName,
      });

      // Handle connection events
      this.client.on("error", (err) => {
        logger.error("MongoDB error", { error: err.message });
      });

      return true;
    } catch (error) {
      logger.error("Failed to connect to MongoDB", { error: error.message });
      this.isConnected = false;
      // Retry connection
      setTimeout(() => this.connect(), 5000);
      return false;
    }
  }

  /**
   * Store raw log payload
   * @param {Object} payload - Webhook payload
   * @param {string} source - CI provider (github, gitlab)
   * @param {boolean} signatureValid - HMAC validation result
   * @returns {string|null} - Inserted document ID
   */
  async storeRawLog(payload, source, signatureValid) {
    if (!this.isConnected || !this.db) {
      logger.warn("MongoDB not connected, log not stored");
      return null;
    }

    try {
      const document = {
        source,
        payload,
        signature_valid: signatureValid,
        received_at: new Date(),
        processed: false,
      };

      const result = await this.db.collection("raw_logs").insertOne(document);

      logger.debug("Raw log stored in MongoDB", {
        id: result.insertedId,
        source,
      });

      return result.insertedId.toString();
    } catch (error) {
      logger.error("Failed to store raw log", { error: error.message });
      return null;
    }
  }

  /**
   * Mark log as processed
   * @param {string} logId - Document ID
   */
  async markProcessed(logId) {
    if (!this.isConnected || !this.db) return false;

    try {
      await this.db
        .collection("raw_logs")
        .updateOne(
          { _id: new ObjectId(logId) },
          { $set: { processed: true, processed_at: new Date() } }
        );
      return true;
    } catch (error) {
      logger.error("Failed to mark log as processed", { error: error.message });
      return false;
    }
  }

  /**
   * Get recent logs
   * @param {number} limit - Number of logs to return
   */
  async getRecentLogs(limit = 10) {
    if (!this.isConnected || !this.db) return [];

    try {
      return await this.db
        .collection("raw_logs")
        .find({})
        .sort({ received_at: -1 })
        .limit(limit)
        .toArray();
    } catch (error) {
      logger.error("Failed to get recent logs", { error: error.message });
      return [];
    }
  }

  /**
   * Get statistics
   */
  async getStats() {
    if (!this.isConnected || !this.db) {
      return { total: 0, processed: 0, pending: 0 };
    }

    try {
      const total = await this.db.collection("raw_logs").countDocuments();
      const processed = await this.db
        .collection("raw_logs")
        .countDocuments({ processed: true });

      return {
        total,
        processed,
        pending: total - processed,
      };
    } catch (error) {
      logger.error("Failed to get stats", { error: error.message });
      return { total: 0, processed: 0, pending: 0 };
    }
  }

  /**
   * Close connection
   */
  async close() {
    try {
      if (this.client) {
        await this.client.close();
      }
      this.isConnected = false;
      logger.info("MongoDB connection closed gracefully");
    } catch (error) {
      logger.error("Error closing MongoDB connection", {
        error: error.message,
      });
    }
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      connected: this.isConnected,
      database: this.db?.databaseName || null,
    };
  }
}

// Singleton instance
module.exports = new MongoDBService();
