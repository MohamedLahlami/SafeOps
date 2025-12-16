"""
SafeOps LogParser - Drain Algorithm Implementation

Drain is an online log parsing algorithm that uses a fixed-depth parse tree
to efficiently extract log templates from unstructured log messages.

Based on: "Drain: An Online Log Parsing Approach with Fixed Depth Tree"
by Pinjia He, Jieming Zhu, Zibin Zheng, and Michael R. Lyu (ICWS 2017)

Reference: https://github.com/logpai/logparser
"""

import re
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from config import config
from logger import logger


@dataclass
class LogCluster:
    """Represents a cluster of similar log messages with a common template."""
    
    template_id: str
    template_tokens: List[str]
    log_ids: List[str] = field(default_factory=list)
    size: int = 0
    
    @property
    def template(self) -> str:
        """Get the template string."""
        return " ".join(self.template_tokens)
    
    def add_log(self, log_id: str) -> None:
        """Add a log entry to this cluster."""
        self.log_ids.append(log_id)
        self.size += 1


class DrainNode:
    """Node in the Drain parse tree."""
    
    def __init__(self, depth: int = 0, digit_or_token: Optional[str] = None):
        self.depth = depth
        self.digit_or_token = digit_or_token
        self.children: Dict[str, 'DrainNode'] = {}
        self.clusters: List[LogCluster] = []


class DrainParser:
    """
    Drain log parser implementation.
    
    Extracts log templates by building a fixed-depth parse tree
    where logs are grouped by length, then by leading tokens.
    """
    
    # Regex patterns for common variable types
    VARIABLE_PATTERNS = [
        (r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TIMESTAMP>'),  # ISO timestamp
        (r'\d{2}:\d{2}:\d{2}', '<TIME>'),  # Time HH:MM:SS
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>'),  # IP address
        (r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', '<UUID>'),  # UUID
        (r'\b[0-9a-fA-F]{40}\b', '<SHA1>'),  # SHA1 hash
        (r'\b[0-9a-fA-F]{64}\b', '<SHA256>'),  # SHA256 hash
        (r'\b0x[0-9a-fA-F]+\b', '<HEX>'),  # Hex numbers
        (r'(?<=[^a-zA-Z0-9])(\-?\+?\d+)(?=[^a-zA-Z0-9])|^(\-?\+?\d+)(?=[^a-zA-Z0-9])', '<NUM>'),  # Numbers
        (r'\b\d+\.\d+\.\d+\b', '<VERSION>'),  # Version numbers
        (r'https?://\S+', '<URL>'),  # URLs
        (r'/[\w./\-]+', '<PATH>'),  # File paths
    ]
    
    def __init__(
        self,
        depth: int = None,
        sim_th: float = None,
        max_children: int = None
    ):
        """
        Initialize Drain parser.
        
        Args:
            depth: Maximum depth of parse tree (default from config)
            sim_th: Similarity threshold for template matching (0-1)
            max_children: Max children per node to prevent explosion
        """
        self.depth = depth or config.DRAIN_DEPTH
        self.sim_th = sim_th or config.DRAIN_SIM_TH
        self.max_children = max_children or config.DRAIN_MAX_CHILDREN
        
        # Root node of parse tree (keyed by log length)
        self.root = DrainNode()
        
        # All clusters indexed by template ID
        self.clusters: Dict[str, LogCluster] = {}
        
        # Compiled regex patterns
        self.compiled_patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.VARIABLE_PATTERNS
        ]
        
        logger.info(
            f"Drain parser initialized: depth={self.depth}, "
            f"sim_th={self.sim_th}, max_children={self.max_children}"
        )
    
    def preprocess(self, log_line: str) -> List[str]:
        """
        Preprocess log line: normalize variables and tokenize.
        
        Args:
            log_line: Raw log line
            
        Returns:
            List of tokens
        """
        # Apply variable patterns
        processed = log_line
        for pattern, replacement in self.compiled_patterns:
            processed = pattern.sub(replacement, processed)
        
        # Tokenize by whitespace and common delimiters
        tokens = re.split(r'[\s=:,;|\[\](){}]+', processed)
        
        # Filter empty tokens
        tokens = [t for t in tokens if t]
        
        return tokens
    
    def get_template_id(self, tokens: List[str]) -> str:
        """Generate a unique template ID from tokens."""
        template_str = " ".join(tokens)
        return hashlib.md5(template_str.encode()).hexdigest()[:12]
    
    def tree_search(self, tokens: List[str]) -> Optional[LogCluster]:
        """
        Search the parse tree for a matching cluster.
        
        Args:
            tokens: Preprocessed log tokens
            
        Returns:
            Matching LogCluster or None
        """
        if not tokens:
            return None
        
        # First level: group by length
        log_length = len(tokens)
        length_key = str(log_length)
        
        if length_key not in self.root.children:
            return None
        
        current_node = self.root.children[length_key]
        
        # Traverse tree by token prefixes
        for depth in range(min(self.depth - 1, log_length)):
            token = tokens[depth]
            
            # Check if token contains digits -> use wildcard
            if self._has_numbers(token):
                token = "<*>"
            
            if token in current_node.children:
                current_node = current_node.children[token]
            elif "<*>" in current_node.children:
                current_node = current_node.children["<*>"]
            else:
                return None
        
        # Search clusters at leaf node
        return self._fast_match(tokens, current_node.clusters)
    
    def _fast_match(
        self, 
        tokens: List[str], 
        clusters: List[LogCluster]
    ) -> Optional[LogCluster]:
        """
        Find the best matching cluster using sequence similarity.
        
        Args:
            tokens: Log tokens to match
            clusters: Candidate clusters
            
        Returns:
            Best matching cluster or None
        """
        best_match = None
        best_sim = -1
        
        for cluster in clusters:
            sim = self._seq_similarity(tokens, cluster.template_tokens)
            if sim > self.sim_th and sim > best_sim:
                best_sim = sim
                best_match = cluster
        
        return best_match
    
    def _seq_similarity(self, seq1: List[str], seq2: List[str]) -> float:
        """
        Calculate sequence similarity between token lists.
        
        Returns ratio of matching tokens (excluding wildcards).
        """
        if len(seq1) != len(seq2):
            return 0.0
        
        matches = 0
        total = 0
        
        for t1, t2 in zip(seq1, seq2):
            if t1 == "<*>" or t2 == "<*>":
                continue
            total += 1
            if t1 == t2:
                matches += 1
        
        return matches / max(total, 1)
    
    def add_to_tree(self, tokens: List[str], cluster: LogCluster) -> None:
        """
        Add a new cluster to the parse tree.
        
        Args:
            tokens: Log tokens
            cluster: New cluster to add
        """
        log_length = len(tokens)
        length_key = str(log_length)
        
        # Create length node if needed
        if length_key not in self.root.children:
            self.root.children[length_key] = DrainNode(depth=1)
        
        current_node = self.root.children[length_key]
        
        # Build tree path
        for depth in range(min(self.depth - 1, log_length)):
            token = tokens[depth]
            
            if self._has_numbers(token):
                token = "<*>"
            
            if token not in current_node.children:
                if len(current_node.children) < self.max_children:
                    current_node.children[token] = DrainNode(depth=depth + 2)
                elif "<*>" not in current_node.children:
                    current_node.children["<*>"] = DrainNode(depth=depth + 2)
                    token = "<*>"
                else:
                    token = "<*>"
            
            current_node = current_node.children[token]
        
        # Add cluster to leaf node
        current_node.clusters.append(cluster)
    
    def update_template(
        self, 
        tokens: List[str], 
        cluster: LogCluster
    ) -> None:
        """
        Update cluster template by generalizing differing tokens.
        
        Args:
            tokens: New log tokens
            cluster: Existing cluster to update
        """
        new_template = []
        
        for t1, t2 in zip(tokens, cluster.template_tokens):
            if t1 == t2:
                new_template.append(t1)
            else:
                new_template.append("<*>")
        
        cluster.template_tokens = new_template
    
    def _has_numbers(self, token: str) -> bool:
        """Check if token contains numeric characters."""
        return bool(re.search(r'\d', token))
    
    def parse(self, log_line: str, log_id: str = None) -> Tuple[str, str, List[str]]:
        """
        Parse a single log line.
        
        Args:
            log_line: Raw log line
            log_id: Optional unique identifier for the log
            
        Returns:
            Tuple of (template_id, template_string, tokens)
        """
        # Preprocess
        tokens = self.preprocess(log_line)
        
        if not tokens:
            return ("empty", "", [])
        
        # Search for existing cluster
        cluster = self.tree_search(tokens)
        
        if cluster is not None:
            # Update template and add log
            self.update_template(tokens, cluster)
            if log_id:
                cluster.add_log(log_id)
        else:
            # Create new cluster
            template_id = self.get_template_id(tokens)
            cluster = LogCluster(
                template_id=template_id,
                template_tokens=tokens.copy()
            )
            if log_id:
                cluster.add_log(log_id)
            
            self.clusters[template_id] = cluster
            self.add_to_tree(tokens, cluster)
        
        return (cluster.template_id, cluster.template, tokens)
    
    def parse_logs(self, log_lines: List[str]) -> List[Dict]:
        """
        Parse multiple log lines.
        
        Args:
            log_lines: List of raw log lines
            
        Returns:
            List of parse results with template info
        """
        results = []
        
        for i, line in enumerate(log_lines):
            if not line.strip():
                continue
                
            template_id, template, tokens = self.parse(line, log_id=str(i))
            
            results.append({
                "line_id": i,
                "raw": line,
                "template_id": template_id,
                "template": template,
                "tokens": tokens
            })
        
        return results
    
    def get_template_distribution(self) -> Dict[str, int]:
        """Get distribution of logs across templates."""
        return {
            cluster.template_id: cluster.size
            for cluster in self.clusters.values()
        }
    
    def get_all_templates(self) -> List[Dict]:
        """Get all discovered templates."""
        return [
            {
                "template_id": cluster.template_id,
                "template": cluster.template,
                "count": cluster.size
            }
            for cluster in self.clusters.values()
        ]


# Singleton instance for reuse
_parser_instance: Optional[DrainParser] = None


def get_parser() -> DrainParser:
    """Get or create the Drain parser singleton."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DrainParser()
    return _parser_instance
