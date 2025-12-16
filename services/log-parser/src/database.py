"""
SafeOps LogParser - Database Services

Handles connections to MongoDB (parsed logs) and PostgreSQL (metrics).
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient
from bson import ObjectId

from config import config
from logger import logger
from feature_extractor import BuildFeatures


class MongoDBService:
    """MongoDB service for storing parsed log data."""
    
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db = None
        self.connected = False
    
    def connect(self) -> bool:
        """Establish MongoDB connection."""
        try:
            logger.info("Connecting to MongoDB...")
            self.client = MongoClient(config.MONGODB_URI)
            self.db = self.client.get_database()
            
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            
            logger.info(f"MongoDB connected: {self.db.name}")
            return True
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            self.connected = False
            return False
    
    def store_parsed_log(
        self, 
        raw_log_id: str,
        templates: list,
        event_ids: list,
        features: Dict[str, Any]
    ) -> Optional[str]:
        """Store parsed log result."""
        if not self.connected:
            return None
        
        try:
            doc = {
                "raw_log_id": ObjectId(raw_log_id) if raw_log_id else None,
                "templates": templates,
                "event_ids": event_ids,
                "features": features,
                "parsed_at": datetime.utcnow()
            }
            
            result = self.db.parsed_logs.insert_one(doc)
            logger.debug(f"Stored parsed log: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store parsed log: {e}")
            return None
    
    def mark_raw_log_processed(self, raw_log_id: str) -> bool:
        """Mark a raw log as processed."""
        if not self.connected or not raw_log_id:
            return False
        
        try:
            self.db.raw_logs.update_one(
                {"_id": ObjectId(raw_log_id)},
                {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to mark raw log processed: {e}")
            return False
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.connected = False
            logger.info("MongoDB connection closed")


class PostgresService:
    """PostgreSQL/TimescaleDB service for storing metrics."""
    
    def __init__(self):
        self.conn = None
        self.connected = False
    
    def connect(self) -> bool:
        """Establish PostgreSQL connection."""
        try:
            logger.info("Connecting to PostgreSQL...")
            self.conn = psycopg2.connect(config.get_postgres_dsn())
            self.conn.autocommit = True
            self.connected = True
            
            logger.info(f"PostgreSQL connected: {config.POSTGRES_DB}")
            return True
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            self.connected = False
            return False
    
    def store_build_metrics(self, features: BuildFeatures) -> Optional[int]:
        """Store build metrics in TimescaleDB."""
        if not self.connected:
            return None
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO build_metrics (
                        build_id, repo_name, branch, commit_sha,
                        duration_seconds, log_line_count, char_density,
                        error_count, warning_count, event_distribution,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    ) RETURNING id
                """, (
                    features.build_id,
                    features.repo_name,
                    features.branch,
                    features.commit_sha,
                    features.duration_seconds,
                    features.log_line_count,
                    features.char_density,
                    features.error_count,
                    features.warning_count,
                    json.dumps({
                        "unique_templates": features.unique_templates,
                        "template_entropy": features.template_entropy,
                        "suspicious_patterns": features.suspicious_pattern_count,
                        "external_ips": features.external_ip_count,
                        "external_urls": features.external_url_count,
                    })
                ))
                
                result = cur.fetchone()
                metric_id = result[0] if result else None
                
                logger.debug(f"Stored build metrics: id={metric_id}, build={features.build_id}")
                return metric_id
                
        except Exception as e:
            logger.error(f"Failed to store build metrics: {e}")
            return None
    
    def close(self):
        """Close PostgreSQL connection."""
        if self.conn:
            self.conn.close()
            self.connected = False
            logger.info("PostgreSQL connection closed")
