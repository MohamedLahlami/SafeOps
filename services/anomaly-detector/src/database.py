"""
SafeOps AnomalyDetector - Database Module

Handles persistence of anomaly detection results to TimescaleDB.
"""

import json
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from config import config
from logger import logger


def convert_numpy_types(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types."""
    if isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    return obj


class DatabaseManager:
    """Manages TimescaleDB connections and anomaly result storage."""
    
    def __init__(self):
        self.connection = None
        self._ensure_tables()
    
    def _get_connection(self):
        """Get database connection, reconnecting if necessary."""
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(
                host=config.POSTGRES_HOST,
                port=config.POSTGRES_PORT,
                database=config.POSTGRES_DB,
                user=config.POSTGRES_USER,
                password=config.POSTGRES_PASSWORD
            )
            self.connection.autocommit = False
        return self.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
    
    def _ensure_tables(self):
        """Ensure required tables exist."""
        try:
            with self.get_cursor() as cursor:
                # Create anomaly_results table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS anomaly_results (
                        id SERIAL,
                        build_id VARCHAR(255) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        is_anomaly BOOLEAN NOT NULL,
                        anomaly_score DOUBLE PRECISION NOT NULL,
                        prediction INTEGER NOT NULL,
                        confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        anomaly_reasons JSONB,
                        top_features JSONB,
                        model_version VARCHAR(50),
                        raw_features JSONB,
                        PRIMARY KEY (id, timestamp)
                    );
                """)
                
                # Add confidence column if missing (migration for existing tables)
                cursor.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'anomaly_results' AND column_name = 'confidence'
                        ) THEN
                            ALTER TABLE anomaly_results ADD COLUMN confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0;
                        END IF;
                    END $$;
                """)
                
                # Convert to hypertable if not already
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 
                        FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'anomaly_results'
                    );
                """)
                
                is_hypertable = cursor.fetchone()['exists']
                
                if not is_hypertable:
                    try:
                        cursor.execute("""
                            SELECT create_hypertable('anomaly_results', 'timestamp', 
                                                     if_not_exists => TRUE);
                        """)
                        logger.info("Created hypertable for anomaly_results")
                    except Exception as e:
                        logger.warning(f"Could not create hypertable: {e}")
                
                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_anomaly_results_build_id 
                    ON anomaly_results (build_id);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_anomaly_results_is_anomaly 
                    ON anomaly_results (is_anomaly) WHERE is_anomaly = TRUE;
                """)
                
                logger.info("Database tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")
            raise
    
    def save_anomaly_result(
        self, 
        result: Dict[str, Any],
        raw_features: Dict[str, Any] = None
    ) -> int:
        """
        Save an anomaly detection result.
        
        Args:
            result: AnomalyResult as dictionary
            raw_features: Original feature values
            
        Returns:
            Inserted record ID
        """
        # Convert all numpy types to native Python types
        result = convert_numpy_types(result)
        
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO anomaly_results (
                    build_id, build_metric_id, is_anomaly, anomaly_score,
                    prediction, confidence, anomaly_reasons, 
                    model_version
                ) VALUES (
                    %(build_id)s, %(build_metric_id)s, %(is_anomaly)s, %(anomaly_score)s,
                    %(prediction)s, %(confidence)s, %(anomaly_reasons)s,
                    %(model_version)s
                )
                RETURNING id;
            """, {
                "build_id": result["build_id"],
                "build_metric_id": 0,  # Default value, can be updated if available
                "is_anomaly": bool(result["is_anomaly"]),
                "anomaly_score": float(result["anomaly_score"]),
                "prediction": int(result["prediction"]),
                "confidence": float(result["confidence"]),
                "anomaly_reasons": json.dumps(convert_numpy_types(result.get("anomaly_reasons", []))),
                "model_version": result.get("model_version", "unknown")
            })
            
            record_id = cursor.fetchone()["id"]
            logger.info(
                f"Saved anomaly result for build {result['build_id']}: "
                f"anomaly={result['is_anomaly']}, score={result['anomaly_score']:.4f}"
            )
            return record_id
    
    def save_anomaly_results_batch(
        self, 
        results: List[Dict[str, Any]]
    ) -> int:
        """Save multiple anomaly results in batch."""
        if not results:
            return 0
        
        values = [
            (
                r["build_id"],
                r.get("processed_at", datetime.utcnow().isoformat()),
                r["is_anomaly"],
                r["anomaly_score"],
                r["prediction"],
                r["confidence"],
                json.dumps(r.get("anomaly_reasons", [])),
                json.dumps(r.get("top_contributing_features", [])),
                r.get("model_version", "unknown"),
                None
            )
            for r in results
        ]
        
        with self.get_cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO anomaly_results (
                    build_id, timestamp, is_anomaly, anomaly_score,
                    prediction, confidence, anomaly_reasons,
                    top_features, model_version, raw_features
                ) VALUES %s
                """,
                values
            )
            
            count = cursor.rowcount
            logger.info(f"Saved {count} anomaly results in batch")
            return count
    
    def get_anomaly_results(
        self,
        limit: int = 100,
        anomalies_only: bool = False,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> List[Dict[str, Any]]:
        """Query anomaly results."""
        with self.get_cursor() as cursor:
            conditions = []
            params = {"limit": limit}
            
            if anomalies_only:
                conditions.append("is_anomaly = TRUE")
            
            if start_time:
                conditions.append("created_at >= %(start_time)s")
                params["start_time"] = start_time
            
            if end_time:
                conditions.append("created_at <= %(end_time)s")
                params["end_time"] = end_time
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            cursor.execute(f"""
                SELECT 
                    id, build_id, created_at as timestamp, is_anomaly, anomaly_score,
                    prediction, confidence, anomaly_reasons,
                    model_version
                FROM anomaly_results
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %(limit)s;
            """, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_anomaly_by_build_id(self, build_id: str) -> Optional[Dict[str, Any]]:
        """Get anomaly result for a specific build."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, build_id, created_at as timestamp, is_anomaly, anomaly_score,
                       prediction, confidence, anomaly_reasons, model_version
                FROM anomaly_results
                WHERE build_id = %s
                ORDER BY created_at DESC
                LIMIT 1;
            """, (build_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_anomaly_stats(
        self, 
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get anomaly statistics for the specified time period."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) as total_builds,
                    COUNT(*) FILTER (WHERE is_anomaly = TRUE) as total_anomalies,
                    AVG(anomaly_score) as avg_score,
                    MIN(anomaly_score) as min_score,
                    MAX(anomaly_score) as max_score,
                    AVG(confidence) as avg_confidence
                FROM anomaly_results
                WHERE created_at > NOW() - INTERVAL '%s hours';
            """, (hours,))
            
            row = cursor.fetchone()
            
            return {
                "period_hours": hours,
                "total_builds": row["total_builds"] or 0,
                "total_anomalies": row["total_anomalies"] or 0,
                "anomaly_rate": (
                    row["total_anomalies"] / row["total_builds"] 
                    if row["total_builds"] > 0 else 0
                ),
                "avg_score": float(row["avg_score"]) if row["avg_score"] else 0,
                "min_score": float(row["min_score"]) if row["min_score"] else 0,
                "max_score": float(row["max_score"]) if row["max_score"] else 0,
                "avg_confidence": float(row["avg_confidence"]) if row["avg_confidence"] else 0,
            }
    
    def get_time_series_data(
        self,
        interval: str = "1 hour",
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get time-bucketed anomaly data for visualization."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    time_bucket(%(interval)s::interval, created_at) as bucket,
                    COUNT(*) as total_builds,
                    COUNT(*) FILTER (WHERE is_anomaly = TRUE) as anomalies,
                    AVG(anomaly_score) as avg_score
                FROM anomaly_results
                WHERE created_at > NOW() - %(hours)s * INTERVAL '1 hour'
                GROUP BY bucket
                ORDER BY bucket;
            """, {"interval": interval, "hours": hours})
            
            return [
                {
                    "time": row["bucket"].isoformat(),
                    "total_builds": row["total_builds"],
                    "anomalies": row["anomalies"],
                    "avg_score": float(row["avg_score"]) if row["avg_score"] else 0
                }
                for row in cursor.fetchall()
            ]
    
    def get_normal_builds_for_training(self, hours: int = 168) -> List[Dict[str, Any]]:
        """
        Get normal (non-anomaly) builds for model retraining.
        
        Returns feature data extracted from raw_features column.
        """
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    build_id,
                    raw_features,
                    created_at
                FROM anomaly_results
                WHERE is_anomaly = FALSE
                  AND raw_features IS NOT NULL
                  AND created_at > NOW() - INTERVAL '%s hours'
                ORDER BY created_at DESC;
            """, (hours,))
            
            results = []
            for row in cursor.fetchall():
                if row["raw_features"]:
                    features = row["raw_features"]
                    if isinstance(features, str):
                        features = json.loads(features)
                    # Add build metadata
                    features["build_id"] = row["build_id"]
                    features["label"] = "normal"  # All are normal
                    results.append(features)
            
            return results
    
    def close(self):
        """Close database connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("Database connection closed")


# Singleton instance
_db_instance: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """Get or create database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
