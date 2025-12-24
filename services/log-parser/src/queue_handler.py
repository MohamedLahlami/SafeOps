"""
SafeOps LogParser - RabbitMQ Message Handler

Consumes raw logs from queue, processes them, and publishes features.
"""

import json
import time
from typing import Callable, Optional

import pika
from pika.adapters.blocking_connection import BlockingChannel

from config import config
from logger import logger


class RabbitMQHandler:
    """Handles RabbitMQ connections for consuming and publishing."""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[BlockingChannel] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Establish RabbitMQ connection."""
        try:
            logger.info("Connecting to RabbitMQ...")
            
            params = pika.URLParameters(config.RABBITMQ_URL)
            params.heartbeat = 600
            params.blocked_connection_timeout = 300
            
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declare queues
            self.channel.queue_declare(queue=config.INPUT_QUEUE, durable=True)
            self.channel.queue_declare(queue=config.OUTPUT_QUEUE, durable=True)
            
            # Set QoS - process one message at a time
            self.channel.basic_qos(prefetch_count=1)
            
            self.connected = True
            logger.info(f"RabbitMQ connected. Input: {config.INPUT_QUEUE}, Output: {config.OUTPUT_QUEUE}")
            return True
            
        except Exception as e:
            logger.error(f"RabbitMQ connection failed: {e}")
            self.connected = False
            return False
    
    def publish(self, queue: str, message: dict) -> bool:
        """Publish message to a queue."""
        if not self.connected or not self.channel:
            logger.warning("Cannot publish - not connected")
            return False
        
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type='application/json'
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            return False
    
    def publish_features(self, features: dict) -> bool:
        """Publish extracted features to output queue."""
        return self.publish(config.OUTPUT_QUEUE, features)
    
    def consume(self, callback: Callable[[dict], bool]) -> None:
        """
        Start consuming messages from input queue.
        
        Args:
            callback: Function to process each message. 
                      Should return True on success, False on failure.
        """
        if not self.connected or not self.channel:
            logger.error("Cannot consume - not connected")
            return
        
        def on_message(ch, method, properties, body):
            try:
                payload = json.loads(body)
                build_id = payload.get("_meta", {}).get("request_id", "unknown")
                
                logger.info(f"Processing message: {build_id}")
                
                # Process the message
                success = callback(payload)
                
                if success:
                    # Acknowledge message
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Message acknowledged: {build_id}")
                else:
                    # Reject and requeue
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    logger.warning(f"Message requeued: {build_id}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON message: {e}")
                ch.basic_ack(delivery_tag=method.delivery_tag)  # Don't requeue bad JSON
            except (AttributeError, TypeError, KeyError) as e:
                logger.error(f"Malformed message data, discarding: {e}")
                ch.basic_ack(delivery_tag=method.delivery_tag)  # Don't requeue malformed data
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
        self.channel.basic_consume(
            queue=config.INPUT_QUEUE,
            on_message_callback=on_message
        )
        
        logger.info(f"Waiting for messages on '{config.INPUT_QUEUE}'...")
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            self.stop()
    
    def stop(self):
        """Stop consuming and close connection."""
        if self.channel:
            self.channel.stop_consuming()
        self.close()
    
    def close(self):
        """Close RabbitMQ connection."""
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
            self.connected = False
            logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
    
    def get_queue_size(self, queue: str) -> int:
        """Get number of messages in a queue."""
        if not self.connected or not self.channel:
            return -1
        
        try:
            result = self.channel.queue_declare(queue=queue, durable=True, passive=True)
            return result.method.message_count
        except Exception:
            return -1
