#!/usr/bin/env python3
"""
Test SafeOps with a real GitHub Actions workflow.
Usage: python scripts/test_real_workflow.py <owner> <repo> <run_id>
"""

import os
import sys
import json
import requests
from datetime import datetime

# Add paths for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data-factory'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'anomaly-detector', 'src'))

from feature_extractor import FeatureExtractor
from model import IsolationForestModel

def fetch_workflow_logs(owner: str, repo: str, run_id: str, token: str) -> dict:
    """Fetch workflow logs from GitHub API."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'SafeOps-LogMiner/1.0'
    }
    
    # Get workflow run details
    run_url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}'
    print(f"Fetching workflow run details from: {run_url}")
    
    run_response = requests.get(run_url, headers=headers)
    if run_response.status_code != 200:
        print(f"Error fetching run: {run_response.status_code}")
        print(run_response.text)
        return None
    
    run_data = run_response.json()
    print(f"Workflow: {run_data.get('name', 'Unknown')}")
    print(f"Status: {run_data.get('status')} / {run_data.get('conclusion')}")
    print(f"Branch: {run_data.get('head_branch')}")
    
    # Get jobs
    jobs_url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs'
    jobs_response = requests.get(jobs_url, headers=headers)
    jobs_data = jobs_response.json() if jobs_response.status_code == 200 else {'jobs': []}
    
    # Download logs (GitHub returns a redirect to a zip file)
    logs_url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs'
    print(f"Fetching logs from: {logs_url}")
    
    logs_response = requests.get(logs_url, headers=headers, allow_redirects=True)
    
    if logs_response.status_code != 200:
        print(f"Error fetching logs: {logs_response.status_code}")
        # Try to get job-level logs as fallback
        raw_logs = ""
        for job in jobs_data.get('jobs', []):
            job_logs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job['id']}/logs"
            job_logs = requests.get(job_logs_url, headers=headers, allow_redirects=True)
            if job_logs.status_code == 200:
                raw_logs += f"\n=== Job: {job['name']} ===\n{job_logs.text}"
        if not raw_logs:
            print("Could not fetch any logs")
            return None
    else:
        # Extract logs from zip
        import zipfile
        import io
        
        try:
            zip_buffer = io.BytesIO(logs_response.content)
            with zipfile.ZipFile(zip_buffer) as zf:
                raw_logs = ""
                for name in zf.namelist():
                    if name.endswith('.txt'):
                        content = zf.read(name).decode('utf-8', errors='replace')
                        raw_logs += f"\n=== {name} ===\n{content}"
                print(f"Extracted {len(zf.namelist())} log files")
        except Exception as e:
            print(f"Error extracting zip: {e}")
            raw_logs = logs_response.text
    
    return {
        'run_data': run_data,
        'jobs': jobs_data.get('jobs', []),
        'raw_logs': raw_logs
    }


def analyze_workflow(workflow_data: dict) -> dict:
    """Extract features and run anomaly detection."""
    run_data = workflow_data['run_data']
    raw_logs = workflow_data['raw_logs']
    
    # Extract features
    print("\n=== Extracting Features ===")
    extractor = FeatureExtractor()
    
    # Parse timestamps
    started_at = None
    finished_at = None
    if run_data.get('run_started_at'):
        started_at = datetime.fromisoformat(run_data['run_started_at'].replace('Z', '+00:00'))
    if run_data.get('updated_at'):
        finished_at = datetime.fromisoformat(run_data['updated_at'].replace('Z', '+00:00'))
    
    features = extractor.extract_from_raw_logs(
        build_id=str(run_data.get('id', 'unknown')),
        repo_name=run_data.get('repository', {}).get('full_name', 'unknown'),
        branch=run_data.get('head_branch', 'unknown'),
        commit_sha=run_data.get('head_sha', 'unknown')[:7],
        raw_logs=raw_logs,
        started_at=started_at,
        finished_at=finished_at
    )
    
    print(f"  log_line_count: {features.log_line_count}")
    print(f"  char_density: {features.char_density:.2f}")
    print(f"  error_count: {features.error_count}")
    print(f"  warning_count: {features.warning_count}")
    print(f"  step_count: {features.step_count}")
    print(f"  suspicious_commands: {features.suspicious_commands}")
    print(f"  unique_ips_contacted: {features.unique_ips_contacted}")
    print(f"  external_urls_count: {features.external_urls_count}")
    print(f"  base64_patterns: {features.base64_patterns}")
    
    # Calculate template entropy from log patterns (simplified)
    lines = raw_logs.split('\n')
    unique_patterns = set()
    for line in lines:
        # Simple template extraction - replace numbers/hashes with placeholders
        import re
        template = re.sub(r'\d+', '<NUM>', line)
        template = re.sub(r'[a-f0-9]{7,}', '<HASH>', template, flags=re.IGNORECASE)
        unique_patterns.add(template[:100])  # Limit template length
    
    unique_templates = len(unique_patterns)
    template_entropy = 0
    if unique_templates > 0:
        import math
        # Shannon entropy calculation
        probs = {}
        for line in lines:
            template = re.sub(r'\d+', '<NUM>', line)
            template = re.sub(r'[a-f0-9]{7,}', '<HASH>', template, flags=re.IGNORECASE)[:100]
            probs[template] = probs.get(template, 0) + 1
        total = sum(probs.values())
        template_entropy = -sum((c/total) * math.log2(c/total) for c in probs.values() if c > 0)
    
    print(f"  unique_templates: {unique_templates}")
    print(f"  template_entropy: {template_entropy:.4f}")
    
    # Convert to model format
    feature_dict = {
        'duration_seconds': features.duration_seconds,
        'log_line_count': features.log_line_count,
        'char_density': features.char_density,
        'error_count': features.error_count,
        'warning_count': features.warning_count,
        'step_count': features.step_count,
        'unique_templates': unique_templates,
        'template_entropy': template_entropy,
        'suspicious_pattern_count': features.suspicious_commands,
        'external_ip_count': features.unique_ips_contacted,
        'external_url_count': features.external_urls_count,
        'base64_pattern_count': features.base64_patterns,
    }
    
    # Run anomaly detection
    print("\n=== Anomaly Detection ===")
    model = IsolationForestModel()
    
    result = model.predict(feature_dict)
    
    print(f"  Is Anomaly: {result.is_anomaly}")
    print(f"  Anomaly Score: {result.anomaly_score:.4f}")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Reasons:")
    for reason in result.anomaly_reasons:
        severity = reason.get('severity', 'info')
        emoji = {'critical': '🚨', 'warning': '⚠️', 'info': 'ℹ️'}.get(severity, '•')
        if 'feature' in reason:
            print(f"    {emoji} {reason['reason']}: {reason['feature']}={reason['value']} (threshold: {reason['threshold']})")
        else:
            print(f"    {emoji} {reason['reason']}")
    
    return {
        'features': feature_dict,
        'result': result.to_dict()
    }


def main():
    # Default to the workflow mentioned by user
    owner = 'qodo-ai'  # Common owner for workflow 20400423555
    repo = 'qodo-cover'  # Common repo
    run_id = '20400423555'
    
    # Override from command line if provided
    if len(sys.argv) >= 4:
        owner = sys.argv[1]
        repo = sys.argv[2]
        run_id = sys.argv[3]
    elif len(sys.argv) == 2:
        run_id = sys.argv[1]
    
    # Get GitHub token from environment
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        # Try to load from .env files
        env_files = [
            os.path.join(os.path.dirname(__file__), '..', '.env'),
            os.path.join(os.path.dirname(__file__), '..', 'services', 'log-collector', '.env'),
        ]
        for env_file in env_files:
            if os.path.exists(env_file):
                with open(env_file) as f:
                    for line in f:
                        if line.startswith('GITHUB_TOKEN='):
                            token = line.strip().split('=', 1)[1].strip('"\'')
                            break
                if token:
                    break
    
    if not token:
        print("Error: GITHUB_TOKEN not found in environment or .env files")
        print("Please set GITHUB_TOKEN environment variable or add it to .env")
        sys.exit(1)
    
    print(f"=== Testing SafeOps with GitHub Workflow ===")
    print(f"Owner: {owner}")
    print(f"Repo: {repo}")
    print(f"Run ID: {run_id}")
    print()
    
    # Fetch workflow data
    workflow_data = fetch_workflow_logs(owner, repo, run_id, token)
    
    if not workflow_data:
        print("Failed to fetch workflow data")
        sys.exit(1)
    
    # Save raw logs for debugging
    log_file = os.path.join(os.path.dirname(__file__), '..', 'data', f'{run_id}.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(workflow_data['raw_logs'])
    print(f"\nSaved raw logs to: {log_file}")
    print(f"Log size: {len(workflow_data['raw_logs'])} characters")
    
    # Analyze
    analysis = analyze_workflow(workflow_data)
    
    # Save results
    result_file = os.path.join(os.path.dirname(__file__), '..', 'data', f'{run_id}_analysis.json')
    with open(result_file, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nSaved analysis to: {result_file}")
    
    # Summary
    print("\n" + "="*50)
    if analysis['result']['is_anomaly']:
        print("⚠️  ANOMALY DETECTED")
    else:
        print("✅ BUILD APPEARS NORMAL")
    print("="*50)


if __name__ == '__main__':
    main()
