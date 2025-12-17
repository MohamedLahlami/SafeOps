"""
SafeOps AnomalyDetector - REST API

Flask API for model serving, predictions, and statistics.
"""

import os
import io
import tempfile
import shutil
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd

from config import config
from logger import logger
from model import get_model
from database import get_database
from queue_handler import get_queue_handler


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    CORS(app)  # Enable CORS for dashboard access
    
    # ========================================
    # Health & Status Endpoints
    # ========================================
    
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        model = get_model()
        return jsonify({
            "status": "healthy",
            "service": "anomaly-detector",
            "model_loaded": model.is_trained,
            "version": model.model_version
        })
    
    @app.route("/status", methods=["GET"])
    def status():
        """Detailed status endpoint."""
        model = get_model()
        handler = get_queue_handler()
        
        return jsonify({
            "service": "anomaly-detector",
            "model": model.get_model_info(),
            "queue": handler.get_queue_info(),
            "processing": {
                "total_processed": handler.processed_count,
                "anomalies_detected": handler.anomaly_count
            }
        })
    
    # ========================================
    # Model Management Endpoints
    # ========================================
    
    @app.route("/model/info", methods=["GET"])
    def model_info():
        """Get model information and configuration."""
        model = get_model()
        return jsonify(model.get_model_info())
    
    @app.route("/model/train", methods=["POST"])
    def train_model():
        """
        Train or retrain the model.
        
        Request body:
        {
            "csv_path": "path/to/training.csv"  // Optional
        }
        """
        model = get_model()
        data = request.get_json() or {}
        
        csv_path = data.get("csv_path", config.TRAINING_DATA_PATH)
        
        if not csv_path:
            return jsonify({"error": "No training data path specified"}), 400
        
        if not os.path.exists(csv_path):
            return jsonify({"error": f"Training file not found: {csv_path}"}), 404
        
        try:
            stats = model.train_from_csv(csv_path)
            return jsonify({
                "status": "success",
                "message": "Model trained successfully",
                "training_stats": stats
            })
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/model/upload", methods=["POST"])
    def upload_training_data():
        """
        Upload CSV training data and train the model.
        
        Accepts multipart/form-data with a 'file' field containing CSV data.
        The CSV should have columns matching the model's expected features.
        """
        model = get_model()
        
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded. Use 'file' field."}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({"error": "Only CSV files are supported"}), 400
        
        try:
            # Read CSV from upload
            content = file.read().decode('utf-8')
            df = pd.read_csv(io.StringIO(content))
            
            logger.info(f"Uploaded training data: {len(df)} rows, columns: {list(df.columns)}")
            
            # Validate required columns
            required_cols = model.FEATURE_NAMES
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                return jsonify({
                    "error": f"Missing required columns: {missing_cols}",
                    "required": required_cols,
                    "provided": list(df.columns)
                }), 400
            
            # Train the model
            stats = model.train(df)
            
            return jsonify({
                "status": "success",
                "message": f"Model trained on {len(df)} samples",
                "training_stats": stats
            })
            
        except Exception as e:
            logger.error(f"Upload training failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/model/retrain-from-normal", methods=["POST"])
    def retrain_from_normal_builds():
        """
        Retrain the model using normal (non-anomaly) builds from the database.
        
        Request body:
        {
            "min_samples": 100,    // Minimum samples required (default 100)
            "hours": 168           // Look back period in hours (default 168 = 1 week)
        }
        """
        model = get_model()
        db = get_database()
        data = request.get_json() or {}
        
        min_samples = data.get("min_samples", 100)
        hours = data.get("hours", 168)  # Default: 1 week
        
        try:
            # Get normal builds from database
            normal_builds = db.get_normal_builds_for_training(hours=hours)
            
            if len(normal_builds) < min_samples:
                return jsonify({
                    "error": f"Insufficient normal builds. Found {len(normal_builds)}, need {min_samples}",
                    "suggestion": "Increase 'hours' parameter or lower 'min_samples'"
                }), 400
            
            # Convert to DataFrame
            df = pd.DataFrame(normal_builds)
            
            logger.info(f"Retraining model with {len(df)} normal builds from last {hours} hours")
            
            # Train the model
            stats = model.train(df)
            
            return jsonify({
                "status": "success",
                "message": f"Model retrained on {len(df)} normal builds",
                "training_stats": stats,
                "data_period_hours": hours
            })
            
        except Exception as e:
            logger.error(f"Retrain from normal builds failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/model/versions", methods=["GET"])
    def list_model_versions():
        """List available model versions."""
        model_dir = os.path.dirname(config.MODEL_PATH)
        
        versions = []
        if os.path.exists(model_dir):
            for f in os.listdir(model_dir):
                if f.endswith('_meta.json'):
                    meta_path = os.path.join(model_dir, f)
                    try:
                        import json
                        with open(meta_path) as mf:
                            meta = json.load(mf)
                            versions.append({
                                "version": meta.get("version", "unknown"),
                                "trained_at": meta.get("trained_at"),
                                "n_samples": meta.get("training_stats", {}).get("n_samples"),
                                "file": f.replace('_meta.json', '.joblib')
                            })
                    except:
                        pass
        
        return jsonify({
            "current_version": get_model().model_version,
            "available_versions": versions
        })
    
    @app.route("/model/backup", methods=["POST"])
    def backup_model():
        """Create a backup of the current model."""
        model = get_model()
        
        if not model.is_trained:
            return jsonify({"error": "No trained model to backup"}), 400
        
        try:
            # Create backup with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(os.path.dirname(config.MODEL_PATH), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            model_name = os.path.basename(config.MODEL_PATH)
            backup_name = f"{model_name.replace('.joblib', '')}_{timestamp}.joblib"
            backup_path = os.path.join(backup_dir, backup_name)
            
            shutil.copy(config.MODEL_PATH, backup_path)
            
            # Copy scaler too
            scaler_path = config.MODEL_PATH.replace('.joblib', '_scaler.joblib')
            if os.path.exists(scaler_path):
                shutil.copy(scaler_path, backup_path.replace('.joblib', '_scaler.joblib'))
            
            # Copy metadata
            meta_path = config.MODEL_PATH.replace('.joblib', '_meta.json')
            if os.path.exists(meta_path):
                shutil.copy(meta_path, backup_path.replace('.joblib', '_meta.json'))
            
            return jsonify({
                "status": "success",
                "backup_path": backup_path,
                "timestamp": timestamp
            })
            
        except Exception as e:
            logger.error(f"Model backup failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    # ========================================
    # Prediction Endpoints
    # ========================================
    
    @app.route("/predict", methods=["POST"])
    def predict():
        """
        Run anomaly detection on provided features.
        
        Request body:
        {
            "build_id": "build-123",
            "features": {
                "duration_seconds": 120,
                "log_line_count": 500,
                ...
            }
        }
        """
        model = get_model()
        
        if not model.is_trained:
            return jsonify({
                "error": "Model not trained. POST to /model/train first."
            }), 503
        
        data = request.get_json()
        
        if not data or "features" not in data:
            return jsonify({"error": "Missing 'features' in request body"}), 400
        
        features = data["features"]
        features["build_id"] = data.get("build_id", "unknown")
        
        try:
            result = model.predict(features)
            
            # Optionally save to database
            if data.get("save", True):
                db = get_database()
                db.save_anomaly_result(result.to_dict(), features)
            
            return jsonify(result.to_dict())
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/predict/batch", methods=["POST"])
    def predict_batch():
        """
        Run anomaly detection on multiple builds.
        
        Request body:
        {
            "builds": [
                {"build_id": "build-1", "features": {...}},
                {"build_id": "build-2", "features": {...}}
            ]
        }
        """
        model = get_model()
        
        if not model.is_trained:
            return jsonify({
                "error": "Model not trained. POST to /model/train first."
            }), 503
        
        data = request.get_json()
        
        if not data or "builds" not in data:
            return jsonify({"error": "Missing 'builds' in request body"}), 400
        
        results = []
        for build in data["builds"]:
            features = build.get("features", {})
            features["build_id"] = build.get("build_id", "unknown")
            
            result = model.predict(features)
            results.append(result.to_dict())
        
        # Save batch to database
        if data.get("save", True):
            db = get_database()
            db.save_anomaly_results_batch(results)
        
        anomaly_count = sum(1 for r in results if r["is_anomaly"])
        
        return jsonify({
            "total": len(results),
            "anomalies": anomaly_count,
            "results": results
        })
    
    # ========================================
    # Query Endpoints (for Dashboard)
    # ========================================
    
    @app.route("/results", methods=["GET"])
    def get_results():
        """
        Query anomaly detection results.
        
        Query params:
        - limit: Max results (default 100)
        - anomalies_only: Only return anomalies (default false)
        """
        db = get_database()
        
        limit = request.args.get("limit", 100, type=int)
        anomalies_only = request.args.get("anomalies_only", "false").lower() == "true"
        
        results = db.get_anomaly_results(
            limit=limit,
            anomalies_only=anomalies_only
        )
        
        return jsonify({
            "count": len(results),
            "results": results
        })
    
    @app.route("/results/<build_id>", methods=["GET"])
    def get_result_by_build(build_id: str):
        """Get anomaly result for a specific build."""
        db = get_database()
        result = db.get_anomaly_by_build_id(build_id)
        
        if not result:
            return jsonify({"error": "Build not found"}), 404
        
        return jsonify(result)
    
    @app.route("/stats", methods=["GET"])
    def get_stats():
        """
        Get anomaly statistics.
        
        Query params:
        - hours: Time period (default 24)
        """
        db = get_database()
        hours = request.args.get("hours", 24, type=int)
        
        stats = db.get_anomaly_stats(hours=hours)
        return jsonify(stats)
    
    @app.route("/timeseries", methods=["GET"])
    def get_timeseries():
        """
        Get time-series data for visualization.
        
        Query params:
        - hours: Time period (default 24)
        - interval: Bucket interval (default "1 hour")
        """
        db = get_database()
        
        hours = request.args.get("hours", 24, type=int)
        interval = request.args.get("interval", "1 hour")
        
        data = db.get_time_series_data(interval=interval, hours=hours)
        return jsonify(data)
    
    # ========================================
    # Queue Management Endpoints
    # ========================================
    
    @app.route("/queue/info", methods=["GET"])
    def queue_info():
        """Get queue status and statistics."""
        handler = get_queue_handler()
        return jsonify(handler.get_queue_info())
    
    @app.route("/queue/process", methods=["POST"])
    def process_queue():
        """
        Process pending messages from the queue.
        
        Request body:
        {
            "count": 10  // Number to process, or "all"
        }
        """
        handler = get_queue_handler()
        data = request.get_json() or {}
        
        count = data.get("count", 1)
        
        if count == "all":
            processed = handler.process_all_pending()
        else:
            processed = 0
            for _ in range(int(count)):
                if handler.process_one():
                    processed += 1
                else:
                    break
        
        return jsonify({
            "processed": processed,
            "queue_status": handler.get_queue_info()
        })
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    logger.info(f"Starting AnomalyDetector API on port {config.API_PORT}")
    app.run(
        host="0.0.0.0",
        port=config.API_PORT,
        debug=config.DEBUG
    )
