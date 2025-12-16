"""
SafeOps LogParser - Main Entry Point

Consumes raw logs from RabbitMQ, parses with Drain algorithm,
extracts features, and publishes to the features queue.
"""

import sys
import signal
import time

from config import config
from logger import logger
from drain import get_parser
from feature_extractor import FeatureExtractor
from queue_handler import RabbitMQHandler
from database import MongoDBService, PostgresService


class LogParserService:
    """Main service orchestrator."""
    
    def __init__(self):
        self.rabbitmq = RabbitMQHandler()
        self.mongodb = MongoDBService()
        self.postgres = PostgresService()
        self.extractor = FeatureExtractor()
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self) -> bool:
        """Initialize connections and start processing."""
        logger.info("Starting LogParser service...")
        logger.info(f"Environment: {config.ENV}")
        
        # Connect to services
        if not self.rabbitmq.connect():
            logger.error("Failed to connect to RabbitMQ")
            return False
        
        if not self.mongodb.connect():
            logger.warning("MongoDB not available - continuing without storage")
        
        if not self.postgres.connect():
            logger.warning("PostgreSQL not available - continuing without metrics storage")
        
        self.running = True
        
        # Show queue status
        input_size = self.rabbitmq.get_queue_size(config.INPUT_QUEUE)
        logger.info(f"Messages waiting in '{config.INPUT_QUEUE}': {input_size}")
        
        # Start consuming
        logger.info("LogParser ready - starting message consumer...")
        self.rabbitmq.consume(self._process_message)
        
        return True
    
    def _process_message(self, payload: dict) -> bool:
        """
        Process a single raw log message.
        
        Args:
            payload: Enriched webhook payload from LogCollector
            
        Returns:
            True on success, False on failure
        """
        try:
            meta = payload.get("_meta", {})
            request_id = meta.get("request_id", "unknown")
            mongo_id = meta.get("mongo_id")
            
            logger.info(f"Processing build: {request_id}")
            start_time = time.time()
            
            # Extract features using Drain parser
            features = self.extractor.extract(payload)
            
            # Get templates from parser
            parser = get_parser()
            templates = parser.get_all_templates()
            template_ids = [t["template_id"] for t in templates[-50:]]  # Last 50 templates
            
            # Store parsed results in MongoDB
            if self.mongodb.connected:
                self.mongodb.store_parsed_log(
                    raw_log_id=mongo_id,
                    templates=templates[-50:],
                    event_ids=template_ids,
                    features=features.to_dict()
                )
                
                # Mark original raw log as processed
                if mongo_id:
                    self.mongodb.mark_raw_log_processed(mongo_id)
            
            # Store metrics in PostgreSQL
            if self.postgres.connected:
                self.postgres.store_build_metrics(features)
            
            # Publish features to output queue for AnomalyDetector
            feature_message = {
                "_meta": {
                    "request_id": request_id,
                    "mongo_id": mongo_id,
                    "source": "log-parser",
                    "processed_at": features.processed_at
                },
                "features": features.to_dict(),
                "feature_vector": features.to_feature_vector(),
                "feature_names": features.feature_names()
            }
            
            published = self.rabbitmq.publish_features(feature_message)
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"Build processed: {features.build_id} | "
                f"Lines: {features.log_line_count} | "
                f"Templates: {features.unique_templates} | "
                f"Suspicious: {features.suspicious_pattern_count} | "
                f"Time: {processing_time:.2f}s | "
                f"Queued: {published}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Stop the service gracefully."""
        logger.info("Stopping LogParser service...")
        self.running = False
        
        self.rabbitmq.stop()
        self.mongodb.close()
        self.postgres.close()
        
        logger.info("LogParser service stopped")
        sys.exit(0)


def main():
    """Main entry point."""
    service = LogParserService()
    
    if not service.start():
        logger.error("Failed to start LogParser service")
        sys.exit(1)


if __name__ == "__main__":
    main()
