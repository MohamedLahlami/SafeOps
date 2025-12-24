#!/usr/bin/env python3
"""Test the fixed model on all saved workflow analyses."""

import sys
import os
import json

sys.path.insert(0, 'services/anomaly-detector/src')
from model import IsolationForestModel

model = IsolationForestModel()
print('Testing model on all saved workflow analyses...')
print()

# Test each analysis file
for f in sorted(os.listdir('data')):
    if f.endswith('_analysis.json'):
        with open(f'data/{f}') as file:
            analysis = json.load(file)
            features = analysis['features']
            if features.get('log_line_count', 0) > 0:
                features['build_id'] = f.replace('_analysis.json', '')
                result = model.predict(features)
                status = 'ANOMALY' if result.is_anomaly else 'NORMAL'
                print(f'{f}:')
                print(f'  Status: {status} (score: {result.anomaly_score:+.4f})')
                print(f'  char_density: {features["char_density"]:.1f}')
                print(f'  suspicious_patterns: {features["suspicious_pattern_count"]}')
                print()

# Test some edge cases
print("=" * 50)
print("Edge Case Tests:")
print("=" * 50)

# Very high char_density (edge of real distribution)
edge_test = {
    'build_id': 'edge_high_density',
    'duration_seconds': 60,
    'log_line_count': 2000,
    'char_density': 150,  # Higher than typical
    'error_count': 10,
    'warning_count': 20,
    'step_count': 5,
    'unique_templates': 300,
    'template_entropy': 7.0,
    'suspicious_pattern_count': 0,
    'external_ip_count': 0,
    'external_url_count': 0,
    'base64_pattern_count': 0
}

result = model.predict(edge_test)
print(f"\nHigh char_density (150): {'ANOMALY' if result.is_anomaly else 'NORMAL'} (score: {result.anomaly_score:+.4f})")

# Test with suspicious patterns (should be anomaly)
suspicious_test = {
    'build_id': 'suspicious_test',
    'duration_seconds': 100,
    'log_line_count': 1500,
    'char_density': 80,
    'error_count': 5,
    'warning_count': 15,
    'step_count': 8,
    'unique_templates': 300,
    'template_entropy': 7.0,
    'suspicious_pattern_count': 3,  # Has suspicious patterns!
    'external_ip_count': 2,
    'external_url_count': 5,
    'base64_pattern_count': 1
}

result = model.predict(suspicious_test)
print(f"With suspicious patterns: {'ANOMALY' if result.is_anomaly else 'NORMAL'} (score: {result.anomaly_score:+.4f})")

# Test cryptomining-like pattern
cryptomining_test = {
    'build_id': 'cryptomining_test',
    'duration_seconds': 1800,  # Very long
    'log_line_count': 800,
    'char_density': 60,
    'error_count': 2,
    'warning_count': 5,
    'step_count': 3,
    'unique_templates': 150,
    'template_entropy': 5.0,
    'suspicious_pattern_count': 5,  # xmrig, etc
    'external_ip_count': 3,  # Mining pool IPs
    'external_url_count': 2,
    'base64_pattern_count': 0
}

result = model.predict(cryptomining_test)
print(f"Cryptomining pattern: {'ANOMALY' if result.is_anomaly else 'NORMAL'} (score: {result.anomaly_score:+.4f})")
