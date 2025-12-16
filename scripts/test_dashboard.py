#!/usr/bin/env python3
"""
Test script to populate the dashboard with sample predictions.
Run this after starting the AnomalyDetector API.
"""

import requests
import random
import time
from datetime import datetime

API_URL = "http://localhost:3002"

# Test builds - mix of normal and anomalous patterns
# Based on training data stats from isolation_forest_meta.json:
#   duration_seconds: mean=120, std=14
#   log_line_count: mean=484, std=102
#   char_density: mean=28.5, std=0.37
#   error_count: mean=14, std=5
#   warning_count: mean=22, std=7
#   step_count: mean=6, std=0

TEST_BUILDS = [
    # Normal builds - matching training distribution
    {"build_id": f"build-normal-{i}", "features": {
        "duration_seconds": random.randint(100, 140),      # ~mean ± 1.5 std
        "log_line_count": random.randint(350, 620),        # ~mean ± 1.5 std
        "char_density": random.uniform(27.8, 29.2),        # ~mean ± 2 std
        "error_count": random.randint(8, 20),              # ~mean ± 1.5 std
        "warning_count": random.randint(12, 32),           # ~mean ± 1.5 std
        "step_count": 6                                    # exact (no variance in training)
    }} for i in range(1, 11)
] + [
    # Cryptomining-like anomalies (very long duration, unusual patterns)
    {"build_id": f"build-crypto-{i}", "features": {
        "duration_seconds": random.randint(300, 600),      # 12+ std above mean!
        "log_line_count": random.randint(50, 200),         # 3+ std below mean
        "char_density": random.uniform(25, 27),            # 4+ std below mean
        "error_count": 0,                                  # 3 std below mean
        "warning_count": random.randint(0, 5),             # 3+ std below mean
        "step_count": random.randint(1, 3)                 # different from training
    }} for i in range(1, 4)
] + [
    # Data exfiltration-like anomalies (high activity patterns)
    {"build_id": f"build-exfil-{i}", "features": {
        "duration_seconds": random.randint(200, 400),      # 6+ std above mean
        "log_line_count": random.randint(1000, 2000),      # 5+ std above mean
        "char_density": random.uniform(30, 35),            # 4+ std above mean
        "error_count": random.randint(30, 50),             # 3+ std above mean
        "warning_count": random.randint(50, 80),           # 4+ std above mean
        "step_count": random.randint(15, 25)               # very different
    }} for i in range(1, 4)
]

def check_health():
    """Check if API is healthy."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        return resp.status_code == 200
    except:
        return False

def send_prediction(build_data):
    """Send a prediction request."""
    try:
        resp = requests.post(
            f"{API_URL}/predict",
            json=build_data,
            timeout=10
        )
        return resp.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    print("=" * 60)
    print("SafeOps Dashboard Test Script")
    print("=" * 60)
    
    # Check API health
    print("\n[1] Checking API health...")
    if not check_health():
        print("❌ API is not running!")
        print("   Start it with: python services/anomaly-detector/src/main.py --api-only")
        return
    print("✅ API is healthy")
    
    # Send test predictions
    print(f"\n[2] Sending {len(TEST_BUILDS)} test builds...")
    
    results = {"normal": 0, "anomaly": 0, "errors": 0}
    
    for i, build in enumerate(TEST_BUILDS, 1):
        result = send_prediction(build)
        
        if result:
            is_anomaly = result.get("is_anomaly", False)
            score = result.get("anomaly_score", 0)
            confidence = result.get("confidence", 0)
            
            status = "🔴 ANOMALY" if is_anomaly else "🟢 Normal"
            print(f"   [{i:2d}/{len(TEST_BUILDS)}] {build['build_id']}: {status} (score={score:.3f}, conf={confidence:.1%})")
            
            if is_anomaly:
                results["anomaly"] += 1
            else:
                results["normal"] += 1
        else:
            results["errors"] += 1
            print(f"   [{i:2d}/{len(TEST_BUILDS)}] {build['build_id']}: ❌ Error")
        
        # Small delay between requests
        time.sleep(0.1)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  ✅ Normal builds:  {results['normal']}")
    print(f"  🔴 Anomalies:      {results['anomaly']}")
    print(f"  ❌ Errors:         {results['errors']}")
    print("=" * 60)
    print("\n🎉 Done! Refresh the dashboard to see the results.")
    print("   Dashboard URL: http://localhost:5174")

if __name__ == "__main__":
    main()
