"""
Feature Extractor Utility

Extracts ML features from raw CI/CD logs.
This module is designed to work with both synthetic data AND real logs
from GitHub Actions / GitLab CI.

When transitioning to real data, only the input parsing needs adjustment -
the feature extraction logic remains the same.
"""

import re
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ExtractedFeatures:
    """Container for extracted ML features."""
    build_id: str
    repo_name: str
    branch: str
    commit_sha: str
    duration_seconds: float
    log_line_count: int
    char_density: float
    error_count: int
    warning_count: int
    step_count: int
    event_distribution: Dict[str, int]
    
    # Additional features for enhanced detection
    unique_ips_contacted: int = 0
    external_urls_count: int = 0
    base64_patterns: int = 0
    suspicious_commands: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DataFrame/JSON serialization."""
        return {
            "build_id": self.build_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "duration_seconds": self.duration_seconds,
            "log_line_count": self.log_line_count,
            "char_density": self.char_density,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "step_count": self.step_count,
            "event_distribution": json.dumps(self.event_distribution),
            "unique_ips_contacted": self.unique_ips_contacted,
            "external_urls_count": self.external_urls_count,
            "base64_patterns": self.base64_patterns,
            "suspicious_commands": self.suspicious_commands
        }
    
    def to_feature_vector(self) -> List[float]:
        """
        Convert to numerical feature vector for Isolation Forest.
        This is the format the ML model expects.
        """
        # Core features
        features = [
            self.duration_seconds,
            self.log_line_count,
            self.char_density,
            self.error_count,
            self.warning_count,
            self.step_count,
        ]
        
        # Event distribution as separate features
        # Normalize by total to get proportions
        total_events = sum(self.event_distribution.values()) or 1
        standard_steps = [
            "checkout", "setup_environment", "install_dependencies",
            "run_tests", "build_artifact", "deploy"
        ]
        for step in standard_steps:
            features.append(self.event_distribution.get(step, 0) / total_events)
        
        # Security-related features
        features.extend([
            self.unique_ips_contacted,
            self.external_urls_count,
            self.base64_patterns,
            self.suspicious_commands
        ])
        
        return features
    
    @staticmethod
    def feature_names() -> List[str]:
        """Return names of features in the same order as to_feature_vector()."""
        return [
            "duration_seconds",
            "log_line_count", 
            "char_density",
            "error_count",
            "warning_count",
            "step_count",
            "event_checkout",
            "event_setup_environment",
            "event_install_dependencies",
            "event_run_tests",
            "event_build_artifact",
            "event_deploy",
            "unique_ips_contacted",
            "external_urls_count",
            "base64_patterns",
            "suspicious_commands"
        ]


class FeatureExtractor:
    """
    Extracts features from CI/CD build logs.
    Works with both synthetic and real data formats.
    """
    
    # Regex patterns for security detection
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')
    BASE64_PATTERN = re.compile(r'base64\s+(?:-d|-decode)?|[A-Za-z0-9+/]{40,}={0,2}')
    
    SUSPICIOUS_COMMANDS = [
        "curl.*POST", "wget.*post", "nc\s+(-e|-c)", 
        "bash\s+-i", "/dev/tcp", "mkfifo",
        "xmrig", "minerd", "cryptonight", "stratum",
        "cat\s+/etc/passwd", "cat\s+/etc/shadow",
        r"\$\(.*\)", "eval\s+"
    ]
    
    ERROR_KEYWORDS = ['error', 'failed', 'failure', 'exception', 'fatal', 'critical']
    WARNING_KEYWORDS = ['warning', 'warn', 'deprecated', 'caution']
    
    def __init__(self):
        self.suspicious_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.SUSPICIOUS_COMMANDS
        ]
    
    def extract_from_webhook(
        self, 
        payload: Dict[str, Any],
        provider: str = "github"
    ) -> ExtractedFeatures:
        """
        Extract features from a webhook payload.
        Supports GitHub Actions and GitLab CI formats.
        """
        if provider == "github":
            return self._extract_github(payload)
        elif provider == "gitlab":
            return self._extract_gitlab(payload)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _extract_github(self, payload: Dict) -> ExtractedFeatures:
        """Extract features from GitHub Actions webhook."""
        workflow_run = payload.get("workflow_run", {})
        repo = payload.get("repository", {})
        extended = payload.get("_safeops_extended", {})
        
        # Parse timestamps
        started_str = workflow_run.get("run_started_at", "")
        finished_str = workflow_run.get("updated_at", "")
        
        try:
            started = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(finished_str.replace("Z", "+00:00"))
            duration = (finished - started).total_seconds()
        except:
            duration = 0
        
        # Get logs from extended data or reconstruct
        raw_logs = extended.get("raw_logs", "")
        steps = extended.get("steps", [])
        
        return self._extract_common(
            build_id=str(workflow_run.get("id", "")),
            repo_name=repo.get("full_name", ""),
            branch=workflow_run.get("head_branch", ""),
            commit_sha=workflow_run.get("head_sha", ""),
            duration=duration,
            raw_logs=raw_logs,
            steps=steps
        )
    
    def _extract_gitlab(self, payload: Dict) -> ExtractedFeatures:
        """Extract features from GitLab CI webhook."""
        attrs = payload.get("object_attributes", {})
        project = payload.get("project", {})
        extended = payload.get("_safeops_extended", {})
        
        duration = attrs.get("duration", 0)
        raw_logs = extended.get("raw_logs", "")
        steps = extended.get("steps", [])
        
        return self._extract_common(
            build_id=str(attrs.get("id", "")),
            repo_name=project.get("path_with_namespace", ""),
            branch=attrs.get("ref", ""),
            commit_sha=attrs.get("sha", ""),
            duration=duration,
            raw_logs=raw_logs,
            steps=steps
        )
    
    def _extract_common(
        self,
        build_id: str,
        repo_name: str,
        branch: str,
        commit_sha: str,
        duration: float,
        raw_logs: str,
        steps: List[Dict]
    ) -> ExtractedFeatures:
        """Common feature extraction logic."""
        
        # Log line analysis
        log_lines = raw_logs.split('\n') if raw_logs else []
        line_count = len(log_lines)
        total_chars = len(raw_logs)
        char_density = total_chars / max(line_count, 1)
        
        # Error/warning counting
        error_count = sum(
            1 for line in log_lines 
            if any(kw in line.lower() for kw in self.ERROR_KEYWORDS)
        )
        warning_count = sum(
            1 for line in log_lines
            if any(kw in line.lower() for kw in self.WARNING_KEYWORDS)
        )
        
        # Event distribution
        event_dist = {}
        for step in steps:
            step_name = step.get("name", "unknown")
            step_lines = step.get("log_lines", [])
            event_dist[step_name] = len(step_lines)
        
        # Security feature extraction
        unique_ips = set(self.IP_PATTERN.findall(raw_logs))
        external_urls = self.URL_PATTERN.findall(raw_logs)
        base64_matches = len(self.BASE64_PATTERN.findall(raw_logs))
        
        suspicious_count = sum(
            len(pattern.findall(raw_logs))
            for pattern in self.suspicious_patterns
        )
        
        return ExtractedFeatures(
            build_id=build_id,
            repo_name=repo_name,
            branch=branch,
            commit_sha=commit_sha,
            duration_seconds=duration,
            log_line_count=line_count,
            char_density=round(char_density, 2),
            error_count=error_count,
            warning_count=warning_count,
            step_count=len(steps),
            event_distribution=event_dist,
            unique_ips_contacted=len(unique_ips),
            external_urls_count=len(external_urls),
            base64_patterns=base64_matches,
            suspicious_commands=suspicious_count
        )
    
    def extract_from_raw_logs(
        self,
        build_id: str,
        repo_name: str,
        branch: str,
        commit_sha: str,
        raw_logs: str,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None
    ) -> ExtractedFeatures:
        """
        Extract features directly from raw log text.
        Use this for real data when full webhook payload isn't available.
        """
        duration = 0
        if started_at and finished_at:
            duration = (finished_at - started_at).total_seconds()
        
        # Try to detect steps from log structure
        steps = self._detect_steps(raw_logs)
        
        return self._extract_common(
            build_id=build_id,
            repo_name=repo_name,
            branch=branch,
            commit_sha=commit_sha,
            duration=duration,
            raw_logs=raw_logs,
            steps=steps
        )
    
    def _detect_steps(self, raw_logs: str) -> List[Dict]:
        """
        Attempt to detect pipeline steps from raw log text.
        Looks for common step markers in GitHub Actions / GitLab CI logs.
        """
        steps = []
        current_step = None
        current_lines = []
        
        # Common step markers
        step_patterns = [
            re.compile(r'^##\[group\](.+)$'),  # GitHub Actions
            re.compile(r'^=== Step: (.+) ===$'),  # Our synthetic format
            re.compile(r'^Running (.+)\.\.\.$'),  # Generic
            re.compile(r'^\s*❯\s*(.+)$'),  # Some CI systems
        ]
        
        for line in raw_logs.split('\n'):
            step_match = None
            for pattern in step_patterns:
                match = pattern.match(line)
                if match:
                    step_match = match.group(1)
                    break
            
            if step_match:
                # Save previous step
                if current_step:
                    steps.append({
                        "name": current_step,
                        "log_lines": current_lines
                    })
                current_step = step_match
                current_lines = [line]
            elif current_step:
                current_lines.append(line)
        
        # Don't forget the last step
        if current_step:
            steps.append({
                "name": current_step,
                "log_lines": current_lines
            })
        
        # If no steps detected, create a single "unknown" step
        if not steps:
            steps = [{
                "name": "unknown",
                "log_lines": raw_logs.split('\n')
            }]
        
        return steps


# Convenience function for quick extraction
def extract_features(
    payload: Dict[str, Any],
    provider: str = "github"
) -> ExtractedFeatures:
    """Quick feature extraction from webhook payload."""
    extractor = FeatureExtractor()
    return extractor.extract_from_webhook(payload, provider)
