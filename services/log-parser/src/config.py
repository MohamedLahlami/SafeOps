"""
SafeOps LogParser - Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from environment variables."""
    
    # Environment
    ENV = os.getenv("NODE_ENV", "development")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # RabbitMQ
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://safeops:safeops123@localhost:5672")
    INPUT_QUEUE = os.getenv("INPUT_QUEUE", "raw_logs")
    OUTPUT_QUEUE = os.getenv("OUTPUT_QUEUE", "features")
    
    # MongoDB
    MONGODB_URI = os.getenv(
        "MONGODB_URI", 
        "mongodb://admin:safeops123@localhost:27017/safeops?authSource=admin"
    )
    
    # PostgreSQL/TimescaleDB
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "safeops_metrics")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "safeops")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "safeops123")
    
    # Drain Algorithm Parameters
    DRAIN_DEPTH = int(os.getenv("DRAIN_DEPTH", "4"))
    DRAIN_SIM_TH = float(os.getenv("DRAIN_SIM_TH", "0.4"))
    DRAIN_MAX_CHILDREN = int(os.getenv("DRAIN_MAX_CHILDREN", "100"))
    
    @classmethod
    def get_postgres_dsn(cls) -> str:
        """Get PostgreSQL connection string."""
        return (
            f"host={cls.POSTGRES_HOST} "
            f"port={cls.POSTGRES_PORT} "
            f"dbname={cls.POSTGRES_DB} "
            f"user={cls.POSTGRES_USER} "
            f"password={cls.POSTGRES_PASSWORD}"
        )


config = Config()
