"""
Diagnose why builds are being classified as anomalies.
Compares feature values against training data baselines.
"""

import requests
import pandas as pd
import json

API_URL = "http://localhost:3002"
TRAINING_DATA = "d:/EMSI/SafeOps5/data-factory/training_data.csv"

def get_training_stats():
    """Load training data and compute statistics"""
    try:
        df = pd.read_csv(TRAINING_DATA)
        # Filter to normal builds only (label == 0 or 'normal')
        if 'label' in df.columns:
            if df['label'].dtype == 'object':
                normal_df = df[df['label'] == 'normal']
            else:
                normal_df = df[df['label'] == 0]
        else:
            normal_df = df
        
        # Get feature columns (exclude non-feature columns)
        exclude_cols = ['build_id', 'label', 'timestamp', 'repository', 'branch']
        feature_cols = [c for c in normal_df.columns if c not in exclude_cols]
        
        stats = {}
        for col in feature_cols:
            stats[col] = {
                'mean': float(normal_df[col].mean()),
                'std': float(normal_df[col].std()),
                'min': float(normal_df[col].min()),
                'max': float(normal_df[col].max()),
                'p25': float(normal_df[col].quantile(0.25)),
                'p75': float(normal_df[col].quantile(0.75)),
            }
        
        return stats, feature_cols
    except Exception as e:
        print(f"Error loading training data: {e}")
        return {}, []


def get_recent_results():
    """Fetch recent prediction results"""
    try:
        response = requests.get(f"{API_URL}/results", params={"limit": 10})
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data.get('results', [])
            return data
    except Exception as e:
        print(f"Error fetching results: {e}")
    return []


def analyze_prediction(result, training_stats, feature_cols):
    """Analyze why a specific build was classified as anomaly"""
    
    build_id = result.get('build_id', 'unknown')
    is_anomaly = result.get('is_anomaly', False)
    confidence = result.get('confidence', 0) * 100
    reasons = result.get('reasons', [])
    features = result.get('features', {})
    
    print(f"\n{'='*70}")
    print(f"Build: {build_id}")
    print(f"Status: {'🔴 ANOMALY' if is_anomaly else '🟢 Normal'} ({confidence:.1f}% confidence)")
    print(f"{'='*70}")
    
    if reasons:
        print(f"\n📋 Flagged Reasons:")
        for r in reasons:
            print(f"   • {r.get('reason', 'Unknown')}")
            if 'value' in r:
                print(f"     Value: {r['value']}")
    
    if features and training_stats:
        print(f"\n📊 Feature Analysis (compared to training baseline):")
        print(f"{'Feature':<25} {'Value':>12} {'Normal Mean':>12} {'Normal Std':>10} {'Z-Score':>10}")
        print("-" * 70)
        
        deviations = []
        for feat in feature_cols:
            if feat in features and feat in training_stats:
                value = features[feat]
                mean = training_stats[feat]['mean']
                std = training_stats[feat]['std']
                
                if std > 0:
                    z_score = (value - mean) / std
                else:
                    z_score = 0
                
                # Flag if z-score is significant (> 2 or < -2)
                flag = "⚠️" if abs(z_score) > 2 else "  "
                
                print(f"{flag} {feat:<23} {value:>12.2f} {mean:>12.2f} {std:>10.2f} {z_score:>10.2f}")
                
                deviations.append((feat, z_score, value, mean))
        
        # Show top deviations
        deviations.sort(key=lambda x: abs(x[1]), reverse=True)
        print(f"\n🎯 Top 3 Deviating Features:")
        for feat, z, val, mean in deviations[:3]:
            direction = "higher" if z > 0 else "lower"
            print(f"   • {feat}: {val:.2f} ({abs(z):.1f}x std {direction} than normal mean {mean:.2f})")
    
    elif not features:
        print("\n⚠️ No feature data available in result")
        print("   This may be because the log-parser extracted different features")
        print("   than what the model was trained on.")


def check_feature_alignment():
    """Check if extracted features match training features"""
    
    print("\n" + "="*70)
    print("🔍 FEATURE ALIGNMENT CHECK")
    print("="*70)
    
    # Get training features
    training_stats, training_features = get_training_stats()
    print(f"\n📚 Training data features ({len(training_features)}):")
    print(f"   {', '.join(training_features)}")
    
    # Get model info
    try:
        response = requests.get(f"{API_URL}/model/info")
        if response.status_code == 200:
            model_info = response.json()
            model_features = model_info.get('features', [])
            print(f"\n🤖 Model expects features ({len(model_features)}):")
            print(f"   {', '.join(model_features)}")
            
            # Check alignment
            training_set = set(training_features)
            model_set = set(model_features)
            
            missing_in_model = training_set - model_set
            extra_in_model = model_set - training_set
            
            if missing_in_model:
                print(f"\n⚠️ Features in training but not in model: {missing_in_model}")
            if extra_in_model:
                print(f"\n⚠️ Features in model but not in training: {extra_in_model}")
            if not missing_in_model and not extra_in_model:
                print(f"\n✅ Features are aligned!")
                
    except Exception as e:
        print(f"\n❌ Could not get model info: {e}")
    
    return training_stats, training_features


def main():
    print("\n🔬 SafeOps-LogMiner Prediction Diagnostics")
    print("="*70)
    
    # Check feature alignment first
    training_stats, feature_cols = check_feature_alignment()
    
    # Get recent results
    results = get_recent_results()
    
    if not results:
        print("\n❌ No prediction results found")
        print("   Run some test predictions first:")
        print("   python scripts/test_github_integration.py --mode simulate")
        return
    
    print(f"\n📈 Analyzing {len(results)} recent predictions...")
    
    # Analyze each result
    for result in results:
        analyze_prediction(result, training_stats, feature_cols)
    
    # Summary
    anomaly_count = sum(1 for r in results if r.get('is_anomaly'))
    print(f"\n{'='*70}")
    print(f"📊 SUMMARY: {anomaly_count}/{len(results)} builds flagged as anomalies")
    print("="*70)
    
    if anomaly_count == len(results):
        print("\n⚠️ ALL builds are being flagged as anomalies!")
        print("   Possible causes:")
        print("   1. Feature mismatch between log-parser output and model training data")
        print("   2. Real GitHub logs have different characteristics than synthetic training data")
        print("   3. Model needs retraining with real log data")
        print("\n   Recommended actions:")
        print("   • Run: python scripts/test_dashboard.py  (uses matching test data)")
        print("   • Or retrain model with real data: POST /model/retrain-from-normal")


if __name__ == "__main__":
    main()