"""
SafeOps AnomalyDetector - Isolation Forest Model

Implements unsupervised anomaly detection using Isolation Forest algorithm.
Designed to detect CI/CD pipeline anomalies like cryptomining and data exfiltration.
"""

import os
import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from config import config
from logger import logger


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single build."""
    
    build_id: str
    is_anomaly: bool
    anomaly_score: float          # Raw score from model (-1 to 1)
    prediction: int               # -1 for anomaly, 1 for normal
    confidence: float             # Confidence level (0-1)
    
    # Explanation for dashboard
    anomaly_reasons: List[Dict[str, Any]]
    
    # Feature contributions
    top_contributing_features: List[Dict[str, float]]
    
    # Metadata
    model_version: str
    processed_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IsolationForestModel:
    """
    Isolation Forest implementation for CI/CD anomaly detection.
    
    The model learns "normal" behavior from historical build data and
    flags builds that deviate significantly from the baseline.
    """
    
    # Feature names expected by the model (must match LogParser output)
    # All 12 features including security-related ones for detecting
    # cryptomining and data exfiltration attacks
    FEATURE_NAMES = [
        # Core features (6)
        "duration_seconds",
        "log_line_count",
        "char_density",
        "error_count",
        "warning_count",
        "step_count",
        # Security features (6)
        "unique_templates",
        "template_entropy",
        "suspicious_pattern_count",
        "external_ip_count",
        "external_url_count",
        "base64_pattern_count",
    ]
    
    # Alias for backwards compatibility
    EXTENDED_FEATURE_NAMES = FEATURE_NAMES
    
    # Thresholds for generating explanations
    # Note: These are for human-readable explanations, not for model decisions.
    # The model uses the actual feature distribution for anomaly detection.
    # These thresholds should be tuned based on your baseline data.
    # Updated with more realistic thresholds based on GitHub Actions logs.
    FEATURE_THRESHOLDS = {
        # Core features - based on typical GitHub Actions builds
        "duration_seconds": {"high": 600, "very_high": 1800, "reason": "Unusually long build duration"},
        "log_line_count": {"high": 8000, "very_high": 15000, "reason": "Excessive log volume"},
        "char_density": {"high": 150, "very_high": 300, "reason": "Unusually dense log lines"},
        "error_count": {"high": 200, "very_high": 500, "reason": "High error count"},
        "warning_count": {"high": 300, "very_high": 600, "reason": "Excessive warnings"},
        "step_count": {"high": 30, "very_high": 50, "reason": "Unusual number of pipeline steps"},
        # Template features (real logs have 200-400 unique templates)
        "unique_templates": {"high": 600, "very_high": 1000, "reason": "Unusual log pattern diversity"},
        "template_entropy": {"high": 8.0, "very_high": 10.0, "reason": "High log randomness (possible obfuscation)"},
        # Security features - CRITICAL for attack detection
        # Normal builds should have 0 for these after the synthetic generator fix
        "suspicious_pattern_count": {"high": 1, "very_high": 5, "reason": "Suspicious command patterns detected"},
        "external_ip_count": {"high": 1, "very_high": 5, "reason": "Multiple external IP connections"},
        "external_url_count": {"high": 10, "very_high": 50, "reason": "Excessive untrusted URL access"},
        "base64_pattern_count": {"high": 5, "very_high": 15, "reason": "Potential data obfuscation"},
    }
    
    def __init__(self):
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
        self.model_version = "1.0.0"
        self.training_stats: Dict[str, Any] = {}
        
        # Try to load existing model
        self._load_model()
    
    def _load_model(self) -> bool:
        """Load model from disk if available."""
        model_path = config.MODEL_PATH
        scaler_path = model_path.replace(".joblib", "_scaler.joblib")
        
        if os.path.exists(model_path) and os.path.exists(scaler_path):
            try:
                self.model = joblib.load(model_path)
                self.scaler = joblib.load(scaler_path)
                self.is_trained = True
                logger.info(f"Loaded model from {model_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
        
        return False
    
    def save_model(self) -> bool:
        """Save model to disk."""
        if not self.is_trained:
            logger.warning("No trained model to save")
            return False
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(config.MODEL_PATH), exist_ok=True)
            
            model_path = config.MODEL_PATH
            scaler_path = model_path.replace(".joblib", "_scaler.joblib")
            
            joblib.dump(self.model, model_path)
            joblib.dump(self.scaler, scaler_path)
            
            # Save metadata
            meta_path = model_path.replace(".joblib", "_meta.json")
            with open(meta_path, 'w') as f:
                json.dump({
                    "version": self.model_version,
                    "trained_at": datetime.utcnow().isoformat(),
                    "feature_names": self.FEATURE_NAMES,
                    "training_stats": self.training_stats,
                    "config": {
                        "n_estimators": config.N_ESTIMATORS,
                        "contamination": config.CONTAMINATION,
                    }
                }, f, indent=2)
            
            logger.info(f"Model saved to {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return False
    
    def train(self, data: pd.DataFrame, feature_columns: List[str] = None) -> Dict[str, Any]:
        """
        Train the Isolation Forest model.
        
        Args:
            data: Training DataFrame with features
            feature_columns: List of feature column names (uses defaults if None)
            
        Returns:
            Training statistics
        """
        feature_cols = feature_columns or self.FEATURE_NAMES
        
        # Validate columns
        available_cols = [c for c in feature_cols if c in data.columns]
        if len(available_cols) < len(feature_cols):
            missing = set(feature_cols) - set(available_cols)
            logger.warning(f"Missing features: {missing}")
        
        # Prepare training data
        X = data[available_cols].copy()
        
        # Handle missing values
        X = X.fillna(X.median())
        
        logger.info(f"Training on {len(X)} samples with {len(available_cols)} features")
        
        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Train Isolation Forest
        self.model = IsolationForest(
            n_estimators=config.N_ESTIMATORS,
            contamination=config.CONTAMINATION,
            random_state=config.RANDOM_STATE,
            n_jobs=-1,  # Use all cores
            warm_start=False
        )
        
        self.model.fit(X_scaled)
        self.is_trained = True
        
        # Calculate training statistics
        predictions = self.model.predict(X_scaled)
        scores = self.model.decision_function(X_scaled)
        
        n_anomalies = (predictions == -1).sum()
        
        self.training_stats = {
            "n_samples": len(X),
            "n_features": len(available_cols),
            "n_anomalies_detected": int(n_anomalies),
            "anomaly_ratio": float(n_anomalies / len(X)),
            "score_mean": float(scores.mean()),
            "score_std": float(scores.std()),
            "feature_means": {col: float(X[col].mean()) for col in available_cols},
            "feature_stds": {col: float(X[col].std()) for col in available_cols},
        }
        
        logger.info(
            f"Training complete: {n_anomalies}/{len(X)} anomalies detected "
            f"({self.training_stats['anomaly_ratio']:.2%})"
        )
        
        # Save the trained model
        self.save_model()
        
        return self.training_stats
    
    def train_from_csv(self, csv_path: str) -> Dict[str, Any]:
        """Train model from CSV file."""
        logger.info(f"Loading training data from {csv_path}")
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Training data not found: {csv_path}")
        
        data = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(data)} records from CSV")
        
        # Filter to normal samples only for unsupervised baseline
        if 'label' in data.columns:
            normal_data = data[data['label'] == 'normal']
            logger.info(f"Using {len(normal_data)} normal samples for training")
            return self.train(normal_data)
        
        return self.train(data)
    
    def predict(self, features: Dict[str, Any]) -> AnomalyResult:
        """
        Predict if a build is anomalous.
        
        Args:
            features: Dictionary of feature values
            
        Returns:
            AnomalyResult with prediction and explanation
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() first.")
        
        build_id = features.get("build_id", "unknown")
        
        # Extract feature vector
        feature_vector = self._extract_feature_vector(features)
        
        # Scale features
        X = np.array([feature_vector])
        X_scaled = self.scaler.transform(X)
        
        # Get prediction and score
        prediction = self.model.predict(X_scaled)[0]
        raw_score = self.model.decision_function(X_scaled)[0]
        
        # Convert score to 0-1 confidence
        # Isolation Forest scores: negative = anomaly, positive = normal
        # More negative = more anomalous
        confidence = self._score_to_confidence(raw_score)
        
        # Convert numpy types to Python native types for database compatibility
        is_anomaly = bool(prediction == -1)
        prediction_int = int(prediction)
        score_float = float(raw_score)
        
        # HYBRID APPROACH: Apply explicit security rules for critical indicators
        # These override ML predictions when critical security features are present
        security_override, override_reasons = self._check_security_rules(features)
        if security_override:
            is_anomaly = True
            # Adjust score to reflect the override
            if score_float > 0:
                score_float = -0.05  # Make it slightly anomalous
        
        # Generate explanations
        reasons = self._generate_reasons(features, is_anomaly)
        if security_override:
            reasons = override_reasons + reasons
        top_features = self._get_top_contributing_features(features, feature_vector)
        
        return AnomalyResult(
            build_id=build_id,
            is_anomaly=is_anomaly,
            anomaly_score=score_float,
            prediction=prediction_int,
            confidence=confidence,
            anomaly_reasons=reasons,
            top_contributing_features=top_features,
            model_version=self.model_version,
            processed_at=datetime.utcnow().isoformat() + "Z"
        )
    
    def _check_security_rules(self, features: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Apply explicit security rules for critical indicators.
        
        These rules catch obvious attack patterns that might be missed by
        the ML model due to feature interactions.
        
        Returns:
            (should_flag, list of reasons)
        """
        reasons = []
        
        # Rule 1: Any suspicious command patterns is a red flag
        suspicious_count = features.get('suspicious_pattern_count', 0) or 0
        if suspicious_count >= 1:
            reasons.append({
                "feature": "suspicious_pattern_count",
                "value": suspicious_count,
                "reason": f"Detected {suspicious_count} suspicious command pattern(s) (e.g., xmrig, nc -e, curl|bash)",
                "severity": "critical"
            })
        
        # Rule 2: External IPs combined with suspicious patterns
        external_ip_count = features.get('external_ip_count', 0) or 0
        if external_ip_count >= 2 and suspicious_count >= 1:
            reasons.append({
                "feature": "external_ip_count", 
                "value": external_ip_count,
                "reason": f"Multiple external IP connections ({external_ip_count}) with suspicious patterns",
                "severity": "critical"
            })
        
        # Rule 3: Very long duration with suspicious patterns (cryptomining indicator)
        duration = features.get('duration_seconds', 0) or 0
        if duration > 1200 and suspicious_count >= 1:  # 20+ minutes with suspicious patterns
            reasons.append({
                "feature": "duration_seconds",
                "value": duration,
                "reason": f"Extended build duration ({duration}s) with suspicious patterns - possible cryptomining",
                "severity": "critical"
            })
        
        return len(reasons) > 0, reasons
    
    def predict_batch(self, feature_list: List[Dict[str, Any]]) -> List[AnomalyResult]:
        """Predict anomalies for multiple builds."""
        return [self.predict(f) for f in feature_list]
    
    def _extract_feature_vector(self, features: Dict[str, Any]) -> List[float]:
        """Extract ordered feature vector from dictionary."""
        vector = []
        for name in self.FEATURE_NAMES:
            value = features.get(name, 0)
            vector.append(float(value) if value is not None else 0.0)
        return vector
    
    def _score_to_confidence(self, score: float) -> float:
        """Convert Isolation Forest score to confidence (0-1)."""
        # Score typically ranges from -0.5 (anomaly) to 0.5 (normal)
        # Transform to 0-1 where higher = more anomalous
        normalized = (0.5 - float(score))  # Invert so higher = more anomalous
        return float(max(0.0, min(1.0, normalized)))
    
    def _generate_reasons(
        self, 
        features: Dict[str, Any], 
        is_anomaly: bool
    ) -> List[Dict[str, Any]]:
        """Generate human-readable reasons for anomaly classification."""
        reasons = []
        
        if not is_anomaly:
            return [{"reason": "Build metrics within normal parameters", "severity": "info"}]
        
        for feature_name, thresholds in self.FEATURE_THRESHOLDS.items():
            value = features.get(feature_name, 0)
            if value is None:
                continue
            
            # Convert to native Python float for database compatibility
            value = float(value)
            
            if value >= thresholds.get("very_high", float('inf')):
                reasons.append({
                    "feature": feature_name,
                    "value": value,
                    "threshold": float(thresholds["very_high"]),
                    "reason": thresholds["reason"],
                    "severity": "critical"
                })
            elif value >= thresholds.get("high", float('inf')):
                reasons.append({
                    "feature": feature_name,
                    "value": value,
                    "threshold": float(thresholds["high"]),
                    "reason": thresholds["reason"],
                    "severity": "warning"
                })
        
        # If no specific reasons found, provide generic explanation
        if not reasons:
            reasons.append({
                "reason": "Unusual combination of build metrics",
                "severity": "warning"
            })
        
        return reasons
    
    def _get_top_contributing_features(
        self, 
        features: Dict[str, Any],
        feature_vector: List[float]
    ) -> List[Dict[str, float]]:
        """
        Get features that contribute most to anomaly score.
        Uses z-score from training distribution.
        """
        if not self.training_stats.get("feature_means"):
            return []
        
        contributions = []
        
        # Use extended features for explanations
        all_features = self.EXTENDED_FEATURE_NAMES
        
        for name in all_features:
            value = features.get(name, 0)
            if value is None:
                value = 0
            
            mean = self.training_stats["feature_means"].get(name, 0)
            std = self.training_stats["feature_stds"].get(name, 1)
            
            if std > 0:
                z_score = abs((float(value) - mean) / std)
            else:
                z_score = 0
            
            contributions.append({
                "feature": name,
                "value": float(value),
                "z_score": round(z_score, 2),
                "deviation": "high" if z_score > 2 else "normal"
            })
        
        # Sort by z-score and return top 5
        contributions.sort(key=lambda x: x["z_score"], reverse=True)
        return contributions[:5]
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status."""
        return {
            "is_trained": self.is_trained,
            "model_version": self.model_version,
            "feature_names": self.FEATURE_NAMES,
            "config": {
                "n_estimators": config.N_ESTIMATORS,
                "contamination": config.CONTAMINATION,
            },
            "training_stats": self.training_stats
        }


# Singleton instance
_model_instance: Optional[IsolationForestModel] = None


def get_model() -> IsolationForestModel:
    """Get or create the model singleton."""
    global _model_instance
    if _model_instance is None:
        _model_instance = IsolationForestModel()
    return _model_instance
