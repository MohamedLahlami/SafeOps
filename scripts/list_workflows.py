import os
import requests

# Load token from .env
with open('.env') as f:
    for line in f:
        if line.startswith('GITHUB_TOKEN='):
            token = line.strip().split('=', 1)[1]
            break

headers = {
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
}

# List repos with actions
repos = requests.get('https://api.github.com/user/repos?per_page=100', headers=headers).json()
print('Repos with workflow runs:')
for repo in repos:
    runs_resp = requests.get(
        f"https://api.github.com/repos/{repo['full_name']}/actions/runs?per_page=3",
        headers=headers
    )
    if runs_resp.status_code == 200:
        data = runs_resp.json()
        if data.get('total_count', 0) > 0:
            print(f"\n{repo['full_name']} ({data['total_count']} total runs):")
            for run in data.get('workflow_runs', [])[:3]:
                print(f"  - ID: {run['id']}, Status: {run['conclusion']}, Branch: {run['head_branch']}")
