"""
SafeOps AnomalyDetector - RabbitMQ Queue Handler

Consumes feature vectors from the LogParser and runs anomaly detection.
"""

import json
import time
from typing import Callable, Optional

import pika
from pika.exceptions import AMQPConnectionError

from config import config
from logger import logger
from model import get_model, AnomalyResult
from database import get_database


class QueueHandler:
    """
    Handles RabbitMQ message consumption for anomaly detection pipeline.
    
    Consumes from: features (published by LogParser)
    Processes each message through Isolation Forest model
    Stores results in TimescaleDB
    """
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.model = get_model()
        self.database = get_database()
        self.processed_count = 0
        self.anomaly_count = 0
    
    def connect(self, retries: int = 5, delay: int = 5) -> bool:
        """Connect to RabbitMQ with retry logic."""
        for attempt in range(retries):
            try:
                credentials = pika.PlainCredentials(
                    config.RABBITMQ_USER,
                    config.RABBITMQ_PASSWORD
                )
                
                parameters = pika.ConnectionParameters(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
                
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                
                # Declare queue (idempotent)
                self.channel.queue_declare(
                    queue=config.FEATURES_QUEUE,
                    durable=True
                )
                
                # Set prefetch to process one message at a time
                self.channel.basic_qos(prefetch_count=1)
                
                logger.info(f"Connected to RabbitMQ at {config.RABBITMQ_HOST}:{config.RABBITMQ_PORT}")
                return True
                
            except AMQPConnectionError as e:
                logger.warning(
                    f"RabbitMQ connection attempt {attempt + 1}/{retries} failed: {e}"
                )
                if attempt < retries - 1:
                    time.sleep(delay)
        
        logger.error("Failed to connect to RabbitMQ")
        return False
    
    def process_message(
        self, 
        channel, 
        method, 
        properties, 
        body: bytes
    ):
        """
        Process a single feature message.
        
        Message format from LogParser:
        {
            "build_id": "...",
            "features": { ... 12 feature values ... },
            "parsed_at": "...",
            "metadata": { ... }
        }
        """
        try:
            message = json.loads(body)
            build_id = message.get("build_id", "unknown")
            features = message.get("features", {})
            
            logger.info(f"Processing features for build: {build_id}")
            
            # Check if model is trained
            if not self.model.is_trained:
                logger.warning(
                    "Model not trained. Attempting to load or train from default data."
                )
                self._ensure_model_trained()
            
            # Run anomaly detection
            features["build_id"] = build_id
            result = self.model.predict(features)
            
            # Log result
            status = "ANOMALY" if result.is_anomaly else "NORMAL"
            logger.info(
                f"Build {build_id}: {status} "
                f"(score={result.anomaly_score:.4f}, confidence={result.confidence:.2f})"
            )
            
            # Save to database
            self.database.save_anomaly_result(
                result=result.to_dict(),
                raw_features=features
            )
            
            # Update counters
            self.processed_count += 1
            if result.is_anomaly:
                self.anomaly_count += 1
            
            # Acknowledge message
            channel.basic_ack(delivery_tag=method.delivery_tag)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in message: {e}")
            # Reject without requeue for invalid messages
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Requeue for transient errors
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def _ensure_model_trained(self):
        """Ensure model is trained, training from default data if needed."""
        if self.model.is_trained:
            return
        
        # Try to train from default training data
        training_path = config.TRAINING_DATA_PATH
        try:
            if training_path:
                self.model.train_from_csv(training_path)
                logger.info("Model trained from default training data")
            else:
                logger.warning("No training data path configured")
        except FileNotFoundError:
            logger.warning(f"Training data not found at {training_path}")
        except Exception as e:
            logger.error(f"Failed to train model: {e}")
    
    def start_consuming(self):
        """Start consuming messages from the features queue."""
        if not self.channel:
            if not self.connect():
                raise RuntimeError("Failed to connect to RabbitMQ")
        
        # Ensure model is ready
        self._ensure_model_trained()
        
        logger.info(f"Starting to consume from queue: {config.FEATURES_QUEUE}")
        logger.info("Waiting for feature messages...")
        
        self.channel.basic_consume(
            queue=config.FEATURES_QUEUE,
            on_message_callback=self.process_message,
            auto_ack=False
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            self.stop()
    
    def process_one(self, timeout: int = 5) -> bool:
        """
        Process a single message with timeout.
        Useful for testing and controlled processing.
        
        Returns:
            True if a message was processed, False if timeout
        """
        if not self.channel:
            if not self.connect():
                return False
        
        # Ensure model is ready
        self._ensure_model_trained()
        
        method, properties, body = self.channel.basic_get(
            queue=config.FEATURES_QUEUE,
            auto_ack=False
        )
        
        if method:
            self.process_message(self.channel, method, properties, body)
            return True
        
        return False
    
    def process_all_pending(self) -> int:
        """
        Process all pending messages in the queue.
        
        Returns:
            Number of messages processed
        """
        count = 0
        while self.process_one():
            count += 1
        
        logger.info(f"Processed {count} pending messages")
        return count
    
    def get_queue_info(self) -> dict:
        """Get queue statistics."""
        if not self.channel:
            if not self.connect():
                return {"error": "Not connected"}
        
        try:
            result = self.channel.queue_declare(
                queue=config.FEATURES_QUEUE,
                durable=True,
                passive=True  # Don't create, just check
            )
            
            return {
                "queue": config.FEATURES_QUEUE,
                "messages": result.method.message_count,
                "consumers": result.method.consumer_count,
                "processed_total": self.processed_count,
                "anomalies_detected": self.anomaly_count
            }
        except Exception as e:
            return {"error": str(e)}
    
    def stop(self):
        """Stop consuming and close connection."""
        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()
        
        if self.connection and self.connection.is_open:
            self.connection.close()
        
        logger.info(
            f"Queue handler stopped. "
            f"Processed: {self.processed_count}, Anomalies: {self.anomaly_count}"
        )


# Singleton instance
_handler_instance: Optional[QueueHandler] = None


def get_queue_handler() -> QueueHandler:
    """Get or create queue handler singleton."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = QueueHandler()
    return _handler_instance
