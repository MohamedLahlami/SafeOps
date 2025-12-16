"""
SafeOps LogParser - Feature Extraction

Extracts numerical features from parsed logs for the Isolation Forest model.
Features are designed to detect anomalies like cryptomining and data exfiltration.
"""

import re
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from drain import DrainParser, get_parser
from logger import logger


@dataclass
class BuildFeatures:
    """
    Feature vector for a single build.
    These features are input to the Isolation Forest model.
    """
    # Identifiers
    build_id: str
    repo_name: str
    branch: str
    commit_sha: str
    
    # Core features (from PRD)
    duration_seconds: float          # T_d: Build duration
    log_line_count: int              # V_l: Log volume
    char_density: float              # D_c: Average chars per line
    error_count: int                 # Error occurrences
    warning_count: int               # Warning occurrences
    
    # Step-based features
    step_count: int                  # Number of pipeline steps
    
    # Template-based features (Bag of Events)
    unique_templates: int            # Number of unique log templates
    template_entropy: float          # Distribution entropy of templates
    
    # Security-related features
    suspicious_pattern_count: int    # Suspicious command patterns
    external_ip_count: int           # Unique external IPs
    external_url_count: int          # External URLs accessed
    base64_pattern_count: int        # Base64 encoded strings
    
    # Metadata
    provider: str                    # github, gitlab, test
    processed_at: str                # ISO timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_feature_vector(self) -> List[float]:
        """
        Convert to numerical vector for ML model.
        Order must match the model's expected input.
        """
        return [
            self.duration_seconds,
            float(self.log_line_count),
            self.char_density,
            float(self.error_count),
            float(self.warning_count),
            float(self.step_count),
            float(self.unique_templates),
            self.template_entropy,
            float(self.suspicious_pattern_count),
            float(self.external_ip_count),
            float(self.external_url_count),
            float(self.base64_pattern_count),
        ]
    
    @staticmethod
    def feature_names() -> List[str]:
        """Feature names in same order as to_feature_vector()."""
        return [
            "duration_seconds",
            "log_line_count",
            "char_density",
            "error_count",
            "warning_count",
            "step_count",
            "unique_templates",
            "template_entropy",
            "suspicious_pattern_count",
            "external_ip_count",
            "external_url_count",
            "base64_pattern_count",
        ]


class FeatureExtractor:
    """
    Extracts ML features from webhook payloads.
    Uses Drain parser for template-based feature extraction.
    """
    
    # Regex patterns for security detection
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')
    BASE64_PATTERN = re.compile(r'base64\s*(-d|-decode)?|[A-Za-z0-9+/]{40,}={0,2}')
    
    # Suspicious command patterns (cryptomining, exfiltration, reverse shells)
    SUSPICIOUS_PATTERNS = [
        re.compile(r'curl.*-X\s*POST', re.IGNORECASE),
        re.compile(r'wget.*--post', re.IGNORECASE),
        re.compile(r'nc\s+(-e|-c)', re.IGNORECASE),
        re.compile(r'bash\s+-i', re.IGNORECASE),
        re.compile(r'/dev/tcp/', re.IGNORECASE),
        re.compile(r'mkfifo', re.IGNORECASE),
        re.compile(r'xmrig|minerd|cryptonight', re.IGNORECASE),
        re.compile(r'stratum\+tcp://', re.IGNORECASE),
        re.compile(r'hashrate', re.IGNORECASE),
        re.compile(r'cat\s+/etc/(passwd|shadow)', re.IGNORECASE),
        re.compile(r'\$\([^)]+\)', re.IGNORECASE),  # Command substitution
    ]
    
    # Error/warning keywords
    ERROR_KEYWORDS = ['error', 'failed', 'failure', 'exception', 'fatal', 'critical']
    WARNING_KEYWORDS = ['warning', 'warn', 'deprecated', 'caution']
    
    def __init__(self, parser: DrainParser = None):
        """
        Initialize feature extractor.
        
        Args:
            parser: Drain parser instance (uses singleton if not provided)
        """
        self.parser = parser or get_parser()
        logger.info("Feature extractor initialized")
    
    def extract(self, payload: Dict[str, Any]) -> BuildFeatures:
        """
        Extract features from a webhook payload.
        
        Args:
            payload: Enriched webhook payload from LogCollector
            
        Returns:
            BuildFeatures instance
        """
        meta = payload.get("_meta", {})
        provider = meta.get("provider", "unknown")
        
        # Extract based on provider format
        if provider == "github" or "workflow_run" in payload:
            return self._extract_github(payload, meta)
        elif provider == "gitlab" or "object_attributes" in payload:
            return self._extract_gitlab(payload, meta)
        else:
            return self._extract_generic(payload, meta)
    
    def _extract_github(
        self, 
        payload: Dict[str, Any],
        meta: Dict[str, Any]
    ) -> BuildFeatures:
        """Extract features from GitHub Actions format."""
        workflow = payload.get("workflow_run", {})
        repo = payload.get("repository", {})
        extended = payload.get("_safeops_extended", {})
        
        # Parse timestamps
        started_str = workflow.get("run_started_at", "")
        finished_str = workflow.get("updated_at", "")
        duration = self._calculate_duration(started_str, finished_str)
        
        # Get raw logs and steps
        raw_logs = extended.get("raw_logs", "")
        steps = extended.get("steps", [])
        
        return self._extract_common(
            build_id=str(workflow.get("id", meta.get("request_id", "unknown"))),
            repo_name=repo.get("full_name", ""),
            branch=workflow.get("head_branch", ""),
            commit_sha=workflow.get("head_sha", ""),
            duration=duration,
            raw_logs=raw_logs,
            steps=steps,
            provider="github",
        )
    
    def _extract_gitlab(
        self, 
        payload: Dict[str, Any],
        meta: Dict[str, Any]
    ) -> BuildFeatures:
        """Extract features from GitLab CI format."""
        attrs = payload.get("object_attributes", {})
        project = payload.get("project", {})
        extended = payload.get("_safeops_extended", {})
        
        duration = attrs.get("duration", 0)
        raw_logs = extended.get("raw_logs", "")
        steps = extended.get("steps", [])
        
        return self._extract_common(
            build_id=str(attrs.get("id", meta.get("request_id", "unknown"))),
            repo_name=project.get("path_with_namespace", ""),
            branch=attrs.get("ref", ""),
            commit_sha=attrs.get("sha", ""),
            duration=float(duration),
            raw_logs=raw_logs,
            steps=steps,
            provider="gitlab",
        )
    
    def _extract_generic(
        self, 
        payload: Dict[str, Any],
        meta: Dict[str, Any]
    ) -> BuildFeatures:
        """Extract features from generic/test format."""
        extended = payload.get("_safeops_extended", {})
        workflow = payload.get("workflow_run", {})
        
        # Try to get timestamps
        started_str = workflow.get("run_started_at", "")
        finished_str = workflow.get("updated_at", "")
        duration = self._calculate_duration(started_str, finished_str)
        
        raw_logs = extended.get("raw_logs", "")
        steps = extended.get("steps", [])
        
        return self._extract_common(
            build_id=str(workflow.get("id", meta.get("request_id", "unknown"))),
            repo_name=payload.get("repository", {}).get("full_name", ""),
            branch=workflow.get("head_branch", ""),
            commit_sha=workflow.get("head_sha", ""),
            duration=duration,
            raw_logs=raw_logs,
            steps=steps,
            provider=meta.get("provider", "unknown"),
        )
    
    def _extract_common(
        self,
        build_id: str,
        repo_name: str,
        branch: str,
        commit_sha: str,
        duration: float,
        raw_logs: str,
        steps: List[Dict],
        provider: str,
    ) -> BuildFeatures:
        """Common feature extraction logic."""
        
        # Log line analysis
        log_lines = raw_logs.split('\n') if raw_logs else []
        # Also collect lines from steps if raw_logs is empty
        if not log_lines or len(log_lines) <= 1:
            log_lines = []
            for step in steps:
                log_lines.extend(step.get("log_lines", []))
        
        line_count = len([l for l in log_lines if l.strip()])
        total_chars = sum(len(line) for line in log_lines)
        char_density = total_chars / max(line_count, 1)
        
        # Error/warning counting
        error_count = self._count_keywords(log_lines, self.ERROR_KEYWORDS)
        warning_count = self._count_keywords(log_lines, self.WARNING_KEYWORDS)
        
        # Parse logs with Drain and get template distribution
        parse_results = self.parser.parse_logs(log_lines)
        unique_templates = len(set(r["template_id"] for r in parse_results))
        template_entropy = self._calculate_entropy(parse_results)
        
        # Security features
        all_text = "\n".join(log_lines)
        suspicious_count = self._count_suspicious_patterns(all_text)
        external_ips = set(self.IP_PATTERN.findall(all_text))
        external_urls = self.URL_PATTERN.findall(all_text)
        base64_count = len(self.BASE64_PATTERN.findall(all_text))
        
        # Filter out private IPs
        public_ips = [ip for ip in external_ips if not self._is_private_ip(ip)]
        
        return BuildFeatures(
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
            unique_templates=unique_templates,
            template_entropy=round(template_entropy, 4),
            suspicious_pattern_count=suspicious_count,
            external_ip_count=len(public_ips),
            external_url_count=len(external_urls),
            base64_pattern_count=base64_count,
            provider=provider,
            processed_at=datetime.utcnow().isoformat() + "Z",
        )
    
    def _calculate_duration(self, start_str: str, end_str: str) -> float:
        """Calculate duration between two ISO timestamps."""
        try:
            if not start_str or not end_str:
                return 0.0
            
            # Handle various timestamp formats
            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                try:
                    start = datetime.strptime(start_str.replace("Z", ""), fmt.replace("Z", ""))
                    end = datetime.strptime(end_str.replace("Z", ""), fmt.replace("Z", ""))
                    return (end - start).total_seconds()
                except ValueError:
                    continue
            
            return 0.0
        except Exception:
            return 0.0
    
    def _count_keywords(self, lines: List[str], keywords: List[str]) -> int:
        """Count lines containing any of the keywords."""
        count = 0
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                count += 1
        return count
    
    def _count_suspicious_patterns(self, text: str) -> int:
        """Count suspicious command patterns."""
        count = 0
        for pattern in self.SUSPICIOUS_PATTERNS:
            count += len(pattern.findall(text))
        return count
    
    def _calculate_entropy(self, parse_results: List[Dict]) -> float:
        """Calculate Shannon entropy of template distribution."""
        import math
        
        if not parse_results:
            return 0.0
        
        # Count template occurrences
        template_counts: Dict[str, int] = {}
        for result in parse_results:
            tid = result["template_id"]
            template_counts[tid] = template_counts.get(tid, 0) + 1
        
        total = len(parse_results)
        entropy = 0.0
        
        for count in template_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        
        return entropy
    
    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is in private range."""
        parts = ip.split('.')
        if len(parts) != 4:
            return True
        
        try:
            first = int(parts[0])
            second = int(parts[1])
            
            # Private ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x, 127.x.x.x
            if first == 10:
                return True
            if first == 172 and 16 <= second <= 31:
                return True
            if first == 192 and second == 168:
                return True
            if first == 127:
                return True
            
            return False
        except ValueError:
            return True
