"""
SafeOps AnomalyDetector - REST API

Flask API for model serving, predictions, and statistics.
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS

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
