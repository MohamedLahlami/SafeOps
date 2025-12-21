"""
SafeOps AnomalyDetector - Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""
    
    # Environment
    ENV = os.getenv("ENV", "development")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # RabbitMQ
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
    RABBITMQ_USER = os.getenv("RABBITMQ_USER", "safeops")
    RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "safeops123")
    FEATURES_QUEUE = os.getenv("FEATURES_QUEUE", "features")
    
    # PostgreSQL/TimescaleDB
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "safeops_metrics")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "safeops")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "safeops123")
    
    # Service paths - resolve absolutely
    _SERVICE_DIR = Path(__file__).resolve().parent.parent
    _PROJECT_ROOT = _SERVICE_DIR.parent.parent
    
    # Model Configuration
    MODEL_PATH = os.getenv("MODEL_PATH", str(_SERVICE_DIR / "models" / "isolation_forest.joblib"))
    # Lower contamination since we're training on curated normal data only
    # 5% is more appropriate than 10% for clean training datasets
    CONTAMINATION = float(os.getenv("CONTAMINATION", "0.05"))
    N_ESTIMATORS = int(os.getenv("N_ESTIMATORS", "100"))
    RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))
    
    # Training - resolve path relative to service directory
    TRAINING_DATA_PATH = os.getenv(
        "TRAINING_DATA_PATH", 
        str(_PROJECT_ROOT / "data-factory" / "output" / "training_data.csv")
    )
    MIN_SAMPLES_FOR_TRAINING = int(os.getenv("MIN_SAMPLES_FOR_TRAINING", "100"))
    
    # API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "3002"))
    
    @classmethod
    def get_postgres_dsn(cls) -> str:
        return (
            f"host={cls.POSTGRES_HOST} "
            f"port={cls.POSTGRES_PORT} "
            f"dbname={cls.POSTGRES_DB} "
            f"user={cls.POSTGRES_USER} "
            f"password={cls.POSTGRES_PASSWORD}"
        )


config = Config()
