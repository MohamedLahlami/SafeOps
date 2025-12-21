"""
Test GitHub Integration with SafeOps-LogMiner

Usage:
  python scripts/test_github_integration.py --mode simulate
  python scripts/test_github_integration.py --mode real --repo owner/repo --run-id 12345678
"""

import argparse
import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone
import random

BASE_URL = "http://localhost:3001"
API_URL = "http://localhost:3002"

def simulate_github_webhook(conclusion="success", duration_seconds=120):
    """Send a simulated GitHub Actions webhook"""
    
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(seconds=duration_seconds)
    
    # Vary the characteristics based on conclusion
    if conclusion == "success":
        build_type = "normal"
    elif conclusion == "failure":
        build_type = "failed"
    else:
        build_type = "anomaly"
    
    workflow_id = random.randint(1000000000, 9999999999)
    
    payload = {
        "action": "completed",
        "workflow_run": {
            "id": workflow_id,
            "name": f"CI Pipeline - {build_type}",
            "head_branch": "main",
            "head_sha": f"{random.randint(100000, 999999):06x}abc123",
            "status": "completed",
            "conclusion": conclusion,
            "created_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_started_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_attempt": 1,
            "jobs_url": f"https://api.github.com/repos/test/repo/actions/runs/{workflow_id}/jobs",
            "logs_url": f"https://api.github.com/repos/test/repo/actions/runs/{workflow_id}/logs",
            "html_url": f"https://github.com/test/repo/actions/runs/{workflow_id}"
        },
        "repository": {
            "id": 123456,
            "full_name": "test-org/test-repo",
            "private": False
        },
        "sender": {
            "login": "test-user"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": f"test-{workflow_id}"
    }
    
    print(f"\n📤 Sending simulated GitHub webhook...")
    print(f"   Workflow ID: {workflow_id}")
    print(f"   Conclusion: {conclusion}")
    print(f"   Duration: {duration_seconds}s")
    
    try:
        response = requests.post(
            f"{BASE_URL}/webhook/github",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        # 200 and 202 are both success codes
        if response.status_code in [200, 202]:
            result = response.json()
            print(f"   ✅ Webhook accepted:")
            print(f"      - Stored: {result.get('stored', 'N/A')}")
            print(f"      - Queued: {result.get('queued', 'N/A')}")
            print(f"      - Logs fetched: {result.get('logs_fetched', 'N/A')}")
            print(f"      - Processing time: {result.get('processing_time_ms', 'N/A')}ms")
            return workflow_id
        else:
            print(f"   ❌ Webhook failed: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection failed - is LogCollector running?")
        return None


def check_anomaly_results(build_id=None, wait_seconds=5):
    """Check if the build was processed and get anomaly results"""
    
    print(f"\n⏳ Waiting {wait_seconds}s for processing...")
    time.sleep(wait_seconds)
    
    print(f"\n📊 Checking anomaly results...")
    
    try:
        response = requests.get(
            f"{API_URL}/results",
            params={"limit": 10, "anomalies_only": False},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Handle both list and dict responses
            if isinstance(data, dict):
                results = data.get('results', [])
                if not results and 'error' not in data:
                    # Maybe the response itself is a single result or has different structure
                    results = [data] if 'build_id' in data else []
            elif isinstance(data, list):
                results = data
            else:
                results = []
            
            print(f"   Found {len(results)} recent results:")
            
            for r in results[:5]:
                if isinstance(r, dict):
                    status = "🔴 ANOMALY" if r.get("is_anomaly") else "🟢 Normal"
                    conf = r.get("confidence", 0) * 100
                    build_id = r.get('build_id', 'unknown')
                    print(f"   - {build_id}: {status} ({conf:.1f}% confidence)")
            
            if not results:
                print("   (No results yet - logs may still be processing)")
            
            return results
        else:
            print(f"   ❌ Failed to get results: {response.status_code} - {response.text}")
            return []
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection failed - is AnomalyDetector running?")
        return []
    except Exception as e:
        print(f"   ❌ Error parsing results: {str(e)}")
        return []


def test_real_github_logs(repo, run_id):
    """Test fetching real GitHub logs (requires GITHUB_TOKEN)"""
    
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN environment variable not set")
        print("   Set it with: $env:GITHUB_TOKEN='ghp_your_token'")
        return False
    
    print(f"\n🔍 Fetching real logs from GitHub...")
    print(f"   Repository: {repo}")
    print(f"   Run ID: {run_id}")
    
    # First, get the workflow run details
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # Get workflow run
        response = requests.get(
            f"https://api.github.com/repos/{repo}/actions/runs/{run_id}",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            run_data = response.json()
            print(f"   ✅ Found workflow: {run_data['name']}")
            print(f"   Status: {run_data['status']}, Conclusion: {run_data['conclusion']}")
            
            # Now send this as a webhook to our system
            webhook_payload = {
                "action": "completed",
                "workflow_run": run_data,
                "repository": {
                    "full_name": repo
                }
            }
            
            webhook_headers = {
                "Content-Type": "application/json",
                "X-GitHub-Event": "workflow_run"
            }
            
            print(f"\n📤 Sending to LogCollector...")
            webhook_response = requests.post(
                f"{BASE_URL}/webhook/github",
                json=webhook_payload,
                headers=webhook_headers,
                timeout=30
            )
            
            if webhook_response.status_code in [200, 202]:
                print(f"   ✅ Webhook processed successfully")
                return True
            else:
                print(f"   ❌ Webhook failed: {webhook_response.text}")
                return False
        else:
            print(f"   ❌ GitHub API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False


def check_services():
    """Check if all services are running"""
    
    print("🔍 Checking services...")
    
    services = [
        ("LogCollector", f"{BASE_URL}/health"),
        ("AnomalyDetector", f"{API_URL}/health"),
    ]
    
    all_healthy = True
    for name, url in services:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"   ✅ {name}: Healthy")
            else:
                print(f"   ⚠️ {name}: Unhealthy ({response.status_code})")
                all_healthy = False
        except:
            print(f"   ❌ {name}: Not reachable")
            all_healthy = False
    
    return all_healthy


def check_queue_status():
    """Check the queue depths"""
    print("\n📬 Checking queue status...")
    
    try:
        response = requests.get(f"{API_URL}/queue/info", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   Features queue: {data.get('queue_depth', 'N/A')} messages pending")
            return data
    except:
        print("   ⚠️ Could not check queue status")
    return {}


def run_simulation_tests():
    """Run a series of simulated webhook tests"""
    
    print("\n" + "="*60)
    print("🧪 SIMULATED GITHUB WEBHOOK TESTS")
    print("="*60)
    
    # Test 1: Normal successful build
    print("\n--- Test 1: Normal successful build ---")
    simulate_github_webhook(conclusion="success", duration_seconds=120)
    
    # Test 2: Failed build
    print("\n--- Test 2: Failed build ---")
    simulate_github_webhook(conclusion="failure", duration_seconds=45)
    
    # Test 3: Long-running build (potential cryptomining)
    print("\n--- Test 3: Long-running build (suspicious) ---")
    simulate_github_webhook(conclusion="success", duration_seconds=900)
    
    # Check queue status
    check_queue_status()
    
    # Check results with longer wait time for processing
    check_anomaly_results(wait_seconds=5)
    
    print("\n" + "="*60)
    print("✅ Simulation tests complete!")
    print("   Open http://localhost to view results in dashboard")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Test GitHub Integration")
    parser.add_argument(
        "--mode",
        choices=["simulate", "real", "check"],
        default="simulate",
        help="Test mode: simulate (fake webhooks), real (fetch actual logs), check (verify services)"
    )
    parser.add_argument("--repo", help="GitHub repo (owner/repo) for real mode")
    parser.add_argument("--run-id", help="Workflow run ID for real mode")
    
    args = parser.parse_args()
    
    print("\n🚀 SafeOps-LogMiner GitHub Integration Test")
    print("="*60)
    
    # Always check services first
    if not check_services():
        print("\n⚠️ Some services are not running!")
        print("   Start them with: docker-compose up -d")
        if args.mode != "check":
            return
    
    if args.mode == "check":
        check_queue_status()
        print("\n✅ Service check complete!")
        
    elif args.mode == "simulate":
        run_simulation_tests()
        
    elif args.mode == "real":
        if not args.repo or not args.run_id:
            print("\n❌ For real mode, provide --repo and --run-id")
            print("   Example: python test_github_integration.py --mode real --repo octocat/hello-world --run-id 12345678")
            return
        
        if test_real_github_logs(args.repo, args.run_id):
            check_anomaly_results(wait_seconds=10)






if __name__ == "__main__":
    main()