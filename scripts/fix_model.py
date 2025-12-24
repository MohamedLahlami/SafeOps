#!/usr/bin/env python3
"""
Fix the anomaly detection model to work with real GitHub Actions workflows.

The issue: Model was trained on synthetic data with char_density ~28,
but real workflows have char_density ~78-125.

Solution: Retrain with augmented data that covers real-world distributions.
"""

import os
import sys
import json
import pandas as pd
import numpy as np

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'anomaly-detector', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data-factory'))

from model import IsolationForestModel


def collect_real_samples():
    """Collect features from real workflow analysis files."""
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    real_samples = []
    
    for f in os.listdir(data_dir):
        if f.endswith('_analysis.json'):
            filepath = os.path.join(data_dir, f)
            with open(filepath) as file:
                analysis = json.load(file)
                features = analysis['features']
                # Only add if it has actual log data
                if features.get('log_line_count', 0) > 0:
                    features['label'] = 'normal'
                    real_samples.append(features)
                    print(f"  {f}: char_density={features['char_density']:.1f}, lines={features['log_line_count']}")
    
    return real_samples


def generate_augmented_samples(n_samples=500):
    """
    Generate augmented samples that bridge synthetic and real distributions.
    
    Real workflow characteristics:
    - char_density: 70-130 (vs synthetic ~28)
    - unique_templates: 300-500 (vs synthetic ~250)
    - duration_seconds: 30-300 (similar)
    - log_line_count: 1000-5000 (similar range)
    """
    np.random.seed(42)
    
    samples = []
    for _ in range(n_samples):
        sample = {
            'duration_seconds': np.random.exponential(120) + 30,  # 30-300+ seconds
            'log_line_count': int(np.random.uniform(500, 5000)),
            'char_density': np.random.uniform(50, 130),  # Bridge synthetic to real
            'error_count': int(np.random.exponential(20)),
            'warning_count': int(np.random.exponential(30)),
            'step_count': int(np.random.uniform(1, 20)),
            'unique_templates': int(np.random.uniform(150, 500)),
            'template_entropy': np.random.uniform(5.5, 8.0),
            # Normal builds have 0 for security features
            'suspicious_pattern_count': 0,
            'external_ip_count': 0,
            'external_url_count': 0,
            'base64_pattern_count': 0,
            'label': 'normal'
        }
        samples.append(sample)
    
    return samples


def main():
    print("=" * 60)
    print("FIXING ANOMALY DETECTION MODEL")
    print("=" * 60)
    
    # 1. Load original synthetic data
    print("\n1. Loading synthetic training data...")
    synthetic_path = os.path.join(os.path.dirname(__file__), '..', 'data-factory', 'output', 'training_data.csv')
    synthetic_df = pd.read_csv(synthetic_path)
    synthetic_normal = synthetic_df[synthetic_df['label'] == 'normal'].copy()
    print(f"   Synthetic normal samples: {len(synthetic_normal)}")
    print(f"   Synthetic char_density mean: {synthetic_normal['char_density'].mean():.1f}")
    
    # 2. Collect real workflow samples
    print("\n2. Collecting real workflow samples...")
    real_samples = collect_real_samples()
    print(f"   Real samples found: {len(real_samples)}")
    
    # 3. Generate augmented samples
    print("\n3. Generating augmented samples...")
    augmented_samples = generate_augmented_samples(500)
    print(f"   Augmented samples: {len(augmented_samples)}")
    
    # 4. Combine all data
    print("\n4. Combining training data...")
    
    # Take subset of synthetic to balance
    synthetic_subset = synthetic_normal.sample(n=min(400, len(synthetic_normal)), random_state=42)
    
    real_df = pd.DataFrame(real_samples)
    augmented_df = pd.DataFrame(augmented_samples)
    
    # Replicate real samples to give them more weight
    if len(real_samples) > 0:
        real_replicated = pd.concat([real_df] * 50, ignore_index=True)  # 50x weight
    else:
        real_replicated = pd.DataFrame()
    
    combined = pd.concat([
        synthetic_subset,
        real_replicated,
        augmented_df
    ], ignore_index=True)
    
    print(f"   Total training samples: {len(combined)}")
    print(f"   Combined char_density range: {combined['char_density'].min():.1f} - {combined['char_density'].max():.1f}")
    print(f"   Combined char_density mean: {combined['char_density'].mean():.1f}")
    
    # 5. Train new model
    print("\n5. Training new model...")
    model = IsolationForestModel()
    
    # Only use feature columns (drop label)
    feature_cols = model.FEATURE_NAMES
    training_data = combined[feature_cols + ['label']]
    
    stats = model.train(training_data[training_data['label'] == 'normal'])
    
    print(f"\n   Training complete!")
    print(f"   Samples used: {stats['n_samples']}")
    print(f"   Anomaly ratio: {stats['anomaly_ratio']:.2%}")
    
    # 6. Test the new model
    print("\n6. Testing new model...")
    
    # Test with synthetic normal
    synthetic_test = {
        'build_id': 'synthetic_test',
        'duration_seconds': 180,
        'log_line_count': 2000,
        'char_density': 28,
        'error_count': 60,
        'warning_count': 90,
        'step_count': 12,
        'unique_templates': 250,
        'template_entropy': 7.2,
        'suspicious_pattern_count': 0,
        'external_ip_count': 0,
        'external_url_count': 0,
        'base64_pattern_count': 0
    }
    
    # Test with real normal
    real_test = {
        'build_id': 'real_test',
        'duration_seconds': 80,
        'log_line_count': 1349,
        'char_density': 78.9,
        'error_count': 5,
        'warning_count': 36,
        'step_count': 1,
        'unique_templates': 365,
        'template_entropy': 6.07,
        'suspicious_pattern_count': 0,
        'external_ip_count': 0,
        'external_url_count': 0,
        'base64_pattern_count': 0
    }
    
    # Test with obvious anomaly
    anomaly_test = {
        'build_id': 'anomaly_test',
        'duration_seconds': 1500,  # Very long
        'log_line_count': 500,
        'char_density': 80,
        'error_count': 10,
        'warning_count': 20,
        'step_count': 5,
        'unique_templates': 300,
        'template_entropy': 7.0,
        'suspicious_pattern_count': 5,  # Suspicious!
        'external_ip_count': 3,  # Suspicious!
        'external_url_count': 10,
        'base64_pattern_count': 2
    }
    
    print("\n   Test Results:")
    print("-" * 50)
    
    for name, test_data in [
        ("Synthetic Normal", synthetic_test),
        ("Real Normal", real_test),
        ("Obvious Anomaly", anomaly_test)
    ]:
        result = model.predict(test_data)
        status = "ANOMALY" if result.is_anomaly else "NORMAL"
        print(f"   {name:20} -> {status:8} (score: {result.anomaly_score:+.4f})")
    
    print("\n" + "=" * 60)
    print("MODEL FIX COMPLETE")
    print("=" * 60)
    
    return model


if __name__ == '__main__':
    main()
