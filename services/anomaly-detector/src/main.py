"""
SafeOps AnomalyDetector - Main Entry Point

Starts the anomaly detection service with both:
1. RabbitMQ queue consumer (background thread)
2. Flask REST API (main thread)
"""

import os
import sys
import time
import signal
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from logger import logger
from model import get_model
from queue_handler import get_queue_handler
from api import app


def train_model_if_needed():
    """Train model from default data if not already trained."""
    model = get_model()
    
    if model.is_trained:
        logger.info("Model already trained and loaded")
        return True
    
    training_path = config.TRAINING_DATA_PATH
    
    if not training_path:
        logger.warning("No training data path configured")
        return False
    
    if not os.path.exists(training_path):
        logger.warning(f"Training data not found: {training_path}")
        return False
    
    try:
        logger.info(f"Training model from {training_path}")
        stats = model.train_from_csv(training_path)
        logger.info(
            f"Model trained: {stats['n_samples']} samples, "
            f"{stats['n_anomalies_detected']} baseline anomalies"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to train model: {e}")
        return False


def start_queue_consumer():
    """Start the queue consumer in a background thread with auto-reconnection."""
    handler = get_queue_handler()
    
    def consumer_thread():
        reconnect_delay = 5  # seconds
        max_delay = 60  # max backoff
        
        while True:
            try:
                logger.info("Queue consumer connecting...")
                handler.connect()
                logger.info("Queue consumer connected, starting to consume messages")
                handler.start_consuming()
            except Exception as e:
                logger.error(f"Queue consumer error: {e}")
                logger.info(f"Reconnecting in {reconnect_delay} seconds...")
                time.sleep(reconnect_delay)
                # Exponential backoff
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            else:
                # Reset delay on successful connection
                reconnect_delay = 5
    
    thread = threading.Thread(target=consumer_thread, daemon=True)
    thread.start()
    logger.info("Queue consumer started in background thread with auto-reconnection")
    return thread


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received")
    handler = get_queue_handler()
    handler.stop()
    sys.exit(0)


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-only', action='store_true', help='Run API only without queue consumer')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("SafeOps AnomalyDetector Service Starting")
    logger.info("=" * 60)
    
    # Train model if needed
    train_model_if_needed()
    
    # Get model status
    model = get_model()
    logger.info(f"Model status: {'READY' if model.is_trained else 'NOT TRAINED'}")
    
    # Check mode
    if args.api_only:
        # API only mode - no queue consumer
        logger.info("Running in API-only mode")
        app.run(
            host="0.0.0.0",
            port=config.API_PORT,
            debug=config.DEBUG
        )
    else:
        # Start queue consumer
        consumer_mode = os.environ.get("CONSUMER_MODE", "background")
        
        if consumer_mode == "only":
            # Run only queue consumer (no API)
            logger.info("Running in consumer-only mode")
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            handler = get_queue_handler()
            handler.connect()
            handler.start_consuming()
        
        else:
            # Run consumer in background, API in foreground
            start_queue_consumer()
            
            # Register signal handlers
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Start Flask API
            logger.info(f"Starting API server on port {config.API_PORT}")
            app.run(
                host="0.0.0.0",
                port=config.API_PORT,
                debug=config.DEBUG,
                use_reloader=False  # Disable reloader to keep consumer thread
            )


if __name__ == "__main__":
    main()
