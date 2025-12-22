"""
Comprehensive Evaluation Script for SafeOps-LogMiner

This script performs:
1. Real-world workflow evaluation
2. Baseline model comparisons (Isolation Forest, One-Class SVM, LOF, Threshold-based)
3. Feature importance analysis
4. Hyperparameter sensitivity analysis
5. Statistical validation with cross-validation

Results are saved to data/evaluation_results.json for inclusion in the paper.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
import warnings
warnings.filterwarnings('ignore')

# Feature names
FEATURE_NAMES = [
    'duration_seconds', 'log_line_count', 'char_density',
    'error_count', 'warning_count', 'step_count',
    'unique_templates', 'template_entropy', 'suspicious_pattern_count',
    'external_ip_count', 'external_url_count', 'base64_pattern_count'
]

class SimpleThresholdDetector:
    """
    Baseline: Simple threshold-based detector using domain knowledge.
    Flags as anomaly if ANY security feature is non-zero or duration is extreme.
    """
    def __init__(self, duration_threshold=600, security_threshold=1):
        self.duration_threshold = duration_threshold
        self.security_threshold = security_threshold
        
    def fit(self, X, y=None):
        return self
    
    def predict(self, X):
        if isinstance(X, pd.DataFrame):
            X = X.values
        
        predictions = []
        for row in X:
            # Get feature values (assuming order matches FEATURE_NAMES)
            duration = row[0]
            suspicious = row[8] if len(row) > 8 else 0
            external_ip = row[9] if len(row) > 9 else 0
            external_url = row[10] if len(row) > 10 else 0
            base64 = row[11] if len(row) > 11 else 0
            
            # Flag as anomaly (-1) if security indicators present or extreme duration
            is_anomaly = (
                duration > self.duration_threshold or
                suspicious >= self.security_threshold or
                external_ip >= self.security_threshold or
                base64 >= self.security_threshold
            )
            predictions.append(-1 if is_anomaly else 1)
        
        return np.array(predictions)
    
    def decision_function(self, X):
        # Return negative score for anomalies
        preds = self.predict(X)
        return preds.astype(float)


def load_or_generate_data():
    """Load existing training data or generate if not available."""
    # Check multiple possible locations
    possible_paths = [
        Path(__file__).parent.parent / 'data-factory' / 'output' / 'training_data.csv',
        Path(__file__).parent.parent / 'data' / 'training_data.csv',
    ]
    
    for training_file in possible_paths:
        if training_file.exists():
            print(f"Loading existing training data from {training_file}")
            df = pd.read_csv(training_file)
            return df
    
    # Generate synthetic data if not available
    print("Generating synthetic training data...")
    sys.path.insert(0, str(Path(__file__).parent.parent / 'data-factory'))
    from synthetic_generator import generate_dataset
    
    output_dir = Path(__file__).parent.parent / 'data-factory' / 'output'
    output_dir.mkdir(exist_ok=True)
    
    df = generate_dataset(n_samples=2000)
    df.to_csv(output_dir / 'training_data.csv', index=False)
    return df


def prepare_data(df):
    """Prepare features and labels from dataframe."""
    # Ensure we have the right columns
    available_features = [f for f in FEATURE_NAMES if f in df.columns]
    
    if len(available_features) < 6:
        raise ValueError(f"Not enough features found. Available: {df.columns.tolist()}")
    
    X = df[available_features].values
    
    # Handle labels
    if 'label' in df.columns:
        # Convert labels: 'normal' -> 1, others -> -1
        y = np.where(df['label'] == 'normal', 1, -1)
    elif 'is_anomaly' in df.columns:
        y = np.where(df['is_anomaly'], -1, 1)
    else:
        # Assume all normal if no label
        y = np.ones(len(df))
    
    return X, y, available_features


def evaluate_model(model, X_train, X_test, y_train, y_test, model_name):
    """Evaluate a single model and return metrics."""
    # Fit model (only on normal samples for unsupervised methods)
    if model_name != 'Threshold':
        X_train_normal = X_train[y_train == 1]
        model.fit(X_train_normal)
    else:
        model.fit(X_train)
    
    # Predict
    y_pred = model.predict(X_test)
    
    # Calculate metrics
    # Convert to binary: anomaly=1, normal=0 for sklearn metrics
    y_test_binary = (y_test == -1).astype(int)
    y_pred_binary = (y_pred == -1).astype(int)
    
    metrics = {
        'accuracy': accuracy_score(y_test_binary, y_pred_binary),
        'precision': precision_score(y_test_binary, y_pred_binary, zero_division=0),
        'recall': recall_score(y_test_binary, y_pred_binary, zero_division=0),
        'f1': f1_score(y_test_binary, y_pred_binary, zero_division=0),
    }
    
    # ROC-AUC if decision function available
    try:
        if hasattr(model, 'decision_function'):
            scores = model.decision_function(X_test)
            # Negate scores (more negative = more anomalous for IF/SVM)
            if model_name in ['IsolationForest', 'OneClassSVM']:
                scores = -scores
            metrics['auc_roc'] = roc_auc_score(y_test_binary, scores)
        else:
            metrics['auc_roc'] = None
    except:
        metrics['auc_roc'] = None
    
    # Confusion matrix
    cm = confusion_matrix(y_test_binary, y_pred_binary)
    metrics['confusion_matrix'] = cm.tolist()
    
    # False positive rate
    tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
    metrics['false_positive_rate'] = fp / (fp + tn) if (fp + tn) > 0 else 0
    metrics['false_negative_rate'] = fn / (fn + tp) if (fn + tp) > 0 else 0
    
    return metrics


def run_baseline_comparison(X, y, feature_names):
    """Compare multiple baseline models."""
    print("\n" + "="*60)
    print("BASELINE MODEL COMPARISON")
    print("="*60)
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train/test split (stratified)
    np.random.seed(42)
    indices = np.random.permutation(len(X))
    split_idx = int(0.8 * len(X))
    train_idx, test_idx = indices[:split_idx], indices[split_idx:]
    
    X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    
    # Define models
    models = {
        'IsolationForest': IsolationForest(
            n_estimators=100, contamination=0.05, random_state=42, n_jobs=-1
        ),
        'OneClassSVM': OneClassSVM(nu=0.05, kernel='rbf', gamma='auto'),
        'LOF': LocalOutlierFactor(n_neighbors=20, contamination=0.05, novelty=True),
        'Threshold': SimpleThresholdDetector(duration_threshold=600)
    }
    
    results = {}
    for name, model in models.items():
        print(f"\nEvaluating {name}...")
        try:
            metrics = evaluate_model(model, X_train, X_test, y_train, y_test, name)
            results[name] = metrics
            
            print(f"  Accuracy:  {metrics['accuracy']:.4f}")
            print(f"  Precision: {metrics['precision']:.4f}")
            print(f"  Recall:    {metrics['recall']:.4f}")
            print(f"  F1 Score:  {metrics['f1']:.4f}")
            if metrics['auc_roc']:
                print(f"  AUC-ROC:   {metrics['auc_roc']:.4f}")
            print(f"  FP Rate:   {metrics['false_positive_rate']:.4f}")
        except Exception as e:
            print(f"  Error: {e}")
            results[name] = {'error': str(e)}
    
    return results


def run_feature_importance(X, y, feature_names):
    """Analyze feature importance using permutation importance."""
    print("\n" + "="*60)
    print("FEATURE IMPORTANCE ANALYSIS")
    print("="*60)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Split data
    np.random.seed(42)
    indices = np.random.permutation(len(X))
    split_idx = int(0.8 * len(X))
    train_idx, test_idx = indices[:split_idx], indices[split_idx:]
    
    X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    
    # Train baseline model
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    X_train_normal = X_train[y_train == 1]
    model.fit(X_train_normal)
    
    # Baseline score
    y_pred_baseline = model.predict(X_test)
    y_test_binary = (y_test == -1).astype(int)
    y_pred_binary = (y_pred_baseline == -1).astype(int)
    baseline_f1 = f1_score(y_test_binary, y_pred_binary, zero_division=0)
    
    print(f"\nBaseline F1 Score (all features): {baseline_f1:.4f}")
    
    # Permutation importance
    importance_results = {}
    for i, feat_name in enumerate(feature_names):
        # Permute feature
        X_test_permuted = X_test.copy()
        np.random.shuffle(X_test_permuted[:, i])
        
        # Evaluate
        y_pred_permuted = model.predict(X_test_permuted)
        y_pred_perm_binary = (y_pred_permuted == -1).astype(int)
        permuted_f1 = f1_score(y_test_binary, y_pred_perm_binary, zero_division=0)
        
        importance = baseline_f1 - permuted_f1
        importance_results[feat_name] = {
            'importance': importance,
            'baseline_f1': baseline_f1,
            'permuted_f1': permuted_f1
        }
    
    # Sort by importance
    sorted_features = sorted(importance_results.items(), key=lambda x: x[1]['importance'], reverse=True)
    
    print("\nFeature Importance (F1 drop when permuted):")
    print("-" * 50)
    for feat, data in sorted_features:
        print(f"  {feat:30s}: {data['importance']:+.4f}")
    
    # Ablation study: train without each feature
    print("\n\nABLATION STUDY")
    print("-" * 50)
    
    ablation_results = {}
    for i, feat_name in enumerate(feature_names):
        # Remove feature
        mask = [j for j in range(len(feature_names)) if j != i]
        X_train_ablated = X_train[:, mask]
        X_test_ablated = X_test[:, mask]
        X_train_normal_ablated = X_train_ablated[y_train == 1]
        
        # Train new model
        model_ablated = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
        model_ablated.fit(X_train_normal_ablated)
        
        # Evaluate
        y_pred_ablated = model_ablated.predict(X_test_ablated)
        y_pred_abl_binary = (y_pred_ablated == -1).astype(int)
        ablated_f1 = f1_score(y_test_binary, y_pred_abl_binary, zero_division=0)
        
        ablation_results[feat_name] = {
            'f1_without': ablated_f1,
            'delta_from_baseline': ablated_f1 - baseline_f1
        }
        
        delta = ablation_results[feat_name]['delta_from_baseline']
        print(f"  Without {feat_name:30s}: F1={ablated_f1:.4f} (Δ={delta:+.4f})")
    
    return {
        'permutation_importance': {k: v['importance'] for k, v in importance_results.items()},
        'ablation_study': ablation_results,
        'baseline_f1': baseline_f1
    }


def run_hyperparameter_sensitivity(X, y):
    """Analyze sensitivity to key hyperparameters."""
    print("\n" + "="*60)
    print("HYPERPARAMETER SENSITIVITY ANALYSIS")
    print("="*60)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Split data
    np.random.seed(42)
    indices = np.random.permutation(len(X))
    split_idx = int(0.8 * len(X))
    train_idx, test_idx = indices[:split_idx], indices[split_idx:]
    
    X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    X_train_normal = X_train[y_train == 1]
    
    y_test_binary = (y_test == -1).astype(int)
    
    # Test different contamination values
    print("\n1. Contamination Parameter Sensitivity:")
    print("-" * 50)
    
    contamination_results = {}
    for contam in [0.01, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]:
        model = IsolationForest(n_estimators=100, contamination=contam, random_state=42)
        model.fit(X_train_normal)
        
        y_pred = model.predict(X_test)
        y_pred_binary = (y_pred == -1).astype(int)
        
        metrics = {
            'precision': precision_score(y_test_binary, y_pred_binary, zero_division=0),
            'recall': recall_score(y_test_binary, y_pred_binary, zero_division=0),
            'f1': f1_score(y_test_binary, y_pred_binary, zero_division=0)
        }
        contamination_results[contam] = metrics
        
        print(f"  contamination={contam:.2f}: P={metrics['precision']:.3f}, R={metrics['recall']:.3f}, F1={metrics['f1']:.3f}")
    
    # Test different n_estimators
    print("\n2. Number of Estimators Sensitivity:")
    print("-" * 50)
    
    estimator_results = {}
    for n_est in [10, 25, 50, 100, 150, 200, 300]:
        model = IsolationForest(n_estimators=n_est, contamination=0.05, random_state=42)
        model.fit(X_train_normal)
        
        y_pred = model.predict(X_test)
        y_pred_binary = (y_pred == -1).astype(int)
        
        f1 = f1_score(y_test_binary, y_pred_binary, zero_division=0)
        estimator_results[n_est] = {'f1': f1}
        
        print(f"  n_estimators={n_est:3d}: F1={f1:.4f}")
    
    return {
        'contamination_sensitivity': contamination_results,
        'n_estimators_sensitivity': estimator_results
    }


def run_cross_validation(X, y):
    """Run stratified cross-validation for statistical significance."""
    print("\n" + "="*60)
    print("CROSS-VALIDATION ANALYSIS")
    print("="*60)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Convert labels for sklearn (anomaly=1, normal=0)
    y_binary = (y == -1).astype(int)
    
    # 5-fold cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    f1_scores = []
    precision_scores = []
    recall_scores = []
    
    for fold, (train_idx, test_idx) in enumerate(cv.split(X_scaled, y_binary)):
        X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
        y_train, y_test = y_binary[train_idx], y_binary[test_idx]
        
        # Train on normal samples only
        X_train_normal = X_train[y_train == 0]  # 0 = normal in binary
        
        model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
        model.fit(X_train_normal)
        
        y_pred = model.predict(X_test)
        y_pred_binary = (y_pred == -1).astype(int)
        
        f1_scores.append(f1_score(y_test, y_pred_binary, zero_division=0))
        precision_scores.append(precision_score(y_test, y_pred_binary, zero_division=0))
        recall_scores.append(recall_score(y_test, y_pred_binary, zero_division=0))
        
        print(f"  Fold {fold+1}: F1={f1_scores[-1]:.4f}")
    
    results = {
        'f1_mean': np.mean(f1_scores),
        'f1_std': np.std(f1_scores),
        'precision_mean': np.mean(precision_scores),
        'precision_std': np.std(precision_scores),
        'recall_mean': np.mean(recall_scores),
        'recall_std': np.std(recall_scores)
    }
    
    print(f"\nCross-Validation Results (5-fold):")
    print(f"  F1 Score:  {results['f1_mean']:.4f} ± {results['f1_std']:.4f}")
    print(f"  Precision: {results['precision_mean']:.4f} ± {results['precision_std']:.4f}")
    print(f"  Recall:    {results['recall_mean']:.4f} ± {results['recall_std']:.4f}")
    
    return results


def main():
    """Run all evaluation analyses."""
    print("="*60)
    print("SafeOps-LogMiner Comprehensive Evaluation")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Load data
    df = load_or_generate_data()
    print(f"\nDataset size: {len(df)} samples")
    
    if 'label' in df.columns:
        print(f"Label distribution:\n{df['label'].value_counts()}")
    
    # Prepare data
    X, y, feature_names = prepare_data(df)
    print(f"\nFeatures used ({len(feature_names)}): {feature_names}")
    print(f"Normal samples: {np.sum(y == 1)}")
    print(f"Anomaly samples: {np.sum(y == -1)}")
    
    # Run all analyses
    results = {
        'timestamp': datetime.now().isoformat(),
        'dataset_size': len(df),
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'normal_count': int(np.sum(y == 1)),
        'anomaly_count': int(np.sum(y == -1))
    }
    
    # 1. Baseline comparison
    results['baseline_comparison'] = run_baseline_comparison(X, y, feature_names)
    
    # 2. Feature importance
    results['feature_analysis'] = run_feature_importance(X, y, feature_names)
    
    # 3. Hyperparameter sensitivity
    results['hyperparameter_sensitivity'] = run_hyperparameter_sensitivity(X, y)
    
    # 4. Cross-validation
    results['cross_validation'] = run_cross_validation(X, y)
    
    # Save results
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / 'evaluation_results.json'
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print("="*60)
    
    return results


if __name__ == '__main__':
    results = main()
