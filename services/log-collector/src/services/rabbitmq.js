/**
 * SafeOps LogCollector - RabbitMQ Service
 * Publishes raw logs to message queue for async processing
 */

const amqp = require("amqplib");
const config = require("../config");
const logger = require("../config/logger");

class RabbitMQService {
  constructor() {
    this.connection = null;
    this.channel = null;
    this.isConnected = false;
  }

  /**
   * Connect to RabbitMQ and create channel
   */
  async connect() {
    try {
      logger.info("Connecting to RabbitMQ...", {
        url: config.rabbitmq.url.replace(/:[^:@]+@/, ":***@"),
      });

      this.connection = await amqp.connect(config.rabbitmq.url);
      this.channel = await this.connection.createChannel();

      // Assert the queue exists
      await this.channel.assertQueue(config.rabbitmq.queue, {
        durable: config.rabbitmq.options.durable,
      });

      this.isConnected = true;
      logger.info("RabbitMQ connected successfully", {
        queue: config.rabbitmq.queue,
      });

      // Handle connection errors
      this.connection.on("error", (err) => {
        logger.error("RabbitMQ connection error", { error: err.message });
        this.isConnected = false;
      });

      this.connection.on("close", () => {
        logger.warn("RabbitMQ connection closed");
        this.isConnected = false;
        // Attempt to reconnect after delay
        setTimeout(() => this.connect(), 5000);
      });

      return true;
    } catch (error) {
      logger.error("Failed to connect to RabbitMQ", { error: error.message });
      this.isConnected = false;
      // Retry connection after delay
      setTimeout(() => this.connect(), 5000);
      return false;
    }
  }

  /**
   * Publish message to the raw_logs queue
   * @param {Object} payload - The log payload to publish
   * @returns {boolean} - Success status
   */
  async publish(payload) {
    if (!this.isConnected || !this.channel) {
      logger.warn("RabbitMQ not connected, message not published");
      return false;
    }

    try {
      const message = Buffer.from(JSON.stringify(payload));

      const sent = this.channel.sendToQueue(config.rabbitmq.queue, message, {
        persistent: config.rabbitmq.options.persistent,
        contentType: "application/json",
        timestamp: Date.now(),
      });

      if (sent) {
        logger.debug("Message published to queue", {
          queue: config.rabbitmq.queue,
          buildId: payload.build_id || payload.workflow_run?.id,
        });
      }

      return sent;
    } catch (error) {
      logger.error("Failed to publish message", { error: error.message });
      return false;
    }
  }

  /**
   * Close connection gracefully
   */
  async close() {
    try {
      if (this.channel) {
        await this.channel.close();
      }
      if (this.connection) {
        await this.connection.close();
      }
      this.isConnected = false;
      logger.info("RabbitMQ connection closed gracefully");
    } catch (error) {
      logger.error("Error closing RabbitMQ connection", {
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
      queue: config.rabbitmq.queue,
    };
  }
}

// Singleton instance
module.exports = new RabbitMQService();
