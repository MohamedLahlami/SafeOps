"""
SafeOps AnomalyDetector - Logging Configuration
"""

import logging
import sys
from config import config


def setup_logging() -> logging.Logger:
    """Configure and return the application logger."""
    
    logger = logging.getLogger("anomaly-detector")
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger


logger = setup_logging()
