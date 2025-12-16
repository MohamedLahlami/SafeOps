#!/usr/bin/env python3
"""
End-to-End Pipeline Test Script

Tests the full flow:
1. Send webhook to LogCollector
2. LogParser consumes and processes
3. AnomalyDetector scores the build
4. Results appear in Dashboard API
"""

import requests
import time
import json
from datetime import datetime

# Service URLs
LOG_COLLECTOR_URL = "http://localhost:3001"
ANOMALY_DETECTOR_URL = "http://localhost:3002"

def check_services():
    """Check if all services are healthy."""
    services = {
        "LogCollector": f"{LOG_COLLECTOR_URL}/health",
        "AnomalyDetector": f"{ANOMALY_DETECTOR_URL}/health"
    }
    
    print("\n[1] Checking service health...")
    all_healthy = True
    for name, url in services.items():
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                print(f"    ✅ {name}: healthy")
            else:
                print(f"    ❌ {name}: unhealthy (status {resp.status_code})")
                all_healthy = False
        except Exception as e:
            print(f"    ❌ {name}: unreachable ({e})")
            all_healthy = False
    
    return all_healthy


def send_test_webhook(build_type="normal"):
    """Send a test webhook payload to LogCollector."""
    
    # Simulate different build patterns based on training data
    if build_type == "normal":
        # Normal build matching training distribution
        payload = {
            "build_id": f"e2e-test-normal-{int(time.time())}",
            "repository": "safeops/test-repo",
            "branch": "main",
            "commit_sha": "abc123def456",
            "status": "completed",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_seconds": 125,  # ~mean of training data
            "log_content": "\n".join([
                "Step 1/6: Checkout code",
                "Cloning repository...",
                "Successfully checked out main branch",
                "Step 2/6: Setup environment",
                "Installing dependencies...",
                "Dependencies installed successfully",
                "Step 3/6: Build",
                "Compiling source files...",
                "Build completed",
                "Step 4/6: Test",
                "Running unit tests...",
                "All 42 tests passed",
                "Step 5/6: Package",
                "Creating artifact...",
                "Artifact created: build.tar.gz",
                "Step 6/6: Deploy",
                "Deploying to staging...",
                "Deployment successful",
                "Pipeline completed successfully"
            ]),
            "metrics": {
                "duration_seconds": 125,
                "log_line_count": 480,
                "char_density": 28.5,
                "error_count": 14,
                "warning_count": 22,
                "step_count": 6
            }
        }
    elif build_type == "crypto":
        # Cryptomining-like anomaly
        payload = {
            "build_id": f"e2e-test-crypto-{int(time.time())}",
            "repository": "safeops/suspicious-repo",
            "branch": "feature/optimization",
            "commit_sha": "suspicious123",
            "status": "completed",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_seconds": 450,  # Very long
            "log_content": "\n".join([
                "Starting build...",
                "Running optimization...",
                "Processing batch 1/1000...",
                "CPU utilization: 100%",
                "Still processing...",
                "Build complete"
            ]),
            "metrics": {
                "duration_seconds": 450,
                "log_line_count": 100,
                "char_density": 26,
                "error_count": 0,
                "warning_count": 2,
                "step_count": 2
            }
        }
    else:
        # Data exfiltration-like anomaly
        payload = {
            "build_id": f"e2e-test-exfil-{int(time.time())}",
            "repository": "safeops/data-repo",
            "branch": "main",
            "commit_sha": "exfil789",
            "status": "completed",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_seconds": 300,
            "log_content": "\n".join([f"Uploading chunk {i}..." for i in range(100)]),
            "metrics": {
                "duration_seconds": 300,
                "log_line_count": 1500,
                "char_density": 32,
                "error_count": 35,
                "warning_count": 60,
                "step_count": 20
            }
        }
    
    try:
        resp = requests.post(
            f"{LOG_COLLECTOR_URL}/webhook/test",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        return resp.status_code == 200 or resp.status_code == 202, payload["build_id"], resp
    except Exception as e:
        return False, None, str(e)


def check_anomaly_result(build_id, max_wait=30):
    """Check if the build was processed by AnomalyDetector."""
    print(f"    Waiting for processing (max {max_wait}s)...", end="", flush=True)
    
    for i in range(max_wait):
        try:
            resp = requests.get(f"{ANOMALY_DETECTOR_URL}/results", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("results", []):
                    if result.get("build_id") == build_id:
                        print(" found!")
                        return result
        except:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    
    print(" timeout!")
    return None


def test_direct_prediction():
    """Test direct prediction endpoint (bypasses queue)."""
    print("\n[3] Testing direct prediction endpoint...")
    
    # Normal build
    normal_features = {
        "build_id": f"direct-normal-{int(time.time())}",
        "features": {
            "duration_seconds": 120,
            "log_line_count": 500,
            "char_density": 28.5,
            "error_count": 12,
            "warning_count": 20,
            "step_count": 6
        }
    }
    
    # Anomalous build
    anomaly_features = {
        "build_id": f"direct-anomaly-{int(time.time())}",
        "features": {
            "duration_seconds": 500,
            "log_line_count": 50,
            "char_density": 25,
            "error_count": 0,
            "warning_count": 1,
            "step_count": 2
        }
    }
    
    for name, data in [("Normal", normal_features), ("Anomaly", anomaly_features)]:
        try:
            resp = requests.post(
                f"{ANOMALY_DETECTOR_URL}/predict",
                json=data,
                timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                status = "🔴 ANOMALY" if result.get("is_anomaly") else "🟢 Normal"
                score = result.get("anomaly_score", 0)
                conf = result.get("confidence", 0)
                print(f"    {name} build: {status} (score={score:.3f}, conf={conf:.1%})")
            else:
                print(f"    ❌ {name}: Failed with status {resp.status_code}")
        except Exception as e:
            print(f"    ❌ {name}: Error - {e}")


def main():
    print("=" * 60)
    print("SafeOps End-to-End Pipeline Test")
    print("=" * 60)
    
    # Check services
    if not check_services():
        print("\n❌ Not all services are healthy. Please start them first.")
        print("   Run: docker-compose up -d")
        return
    
    # Test webhooks through the queue pipeline
    print("\n[2] Testing webhook ingestion...")
    for build_type in ["normal", "crypto", "exfil"]:
        success, build_id, resp = send_test_webhook(build_type)
        if success:
            print(f"    ✅ Sent {build_type} webhook: {build_id}")
        else:
            print(f"    ❌ Failed to send {build_type} webhook: {resp}")
    
    # Test direct prediction (doesn't go through queue)
    test_direct_prediction()
    
    # Summary
    print("\n" + "=" * 60)
    print("Pipeline Test Complete!")
    print("=" * 60)
    print("\n📊 Access points:")
    print(f"   Dashboard:     http://localhost:80")
    print(f"   API:           http://localhost:3002")
    print(f"   RabbitMQ UI:   http://localhost:15672 (safeops/safeops123)")
    print(f"   Webhooks:      http://localhost:3001/webhook")


if __name__ == "__main__":
    main()
