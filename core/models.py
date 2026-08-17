"""
Shared data models used across the entire monitoring pipeline.
Every collector, evaluator, and reporter should produce/consume these
shapes so modules stay decoupled from each other.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Status(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"  # collector failed / no data

@dataclass
class MetricResult:
    name: str
    value: Optional[float]
    display_value: str
    status: Status
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    source: str = ""
    tcode: Optional[str] = None
    detail: str = ""
    screenshot_path: Optional[str] = None
    screenshot_paths: list = field(default_factory=list)   # NEW: all screenshots (e.g. ST22 has 2)
    extra_data: dict = field(default_factory=dict)          # NEW: real extracted values
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class AIAnalysis:
    severity: str = ""
    likely_root_cause: str = ""
    evidence: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    confidence: str = ""
    raw_response: str = ""


@dataclass
class MonitoringResult:
    """The output of one full monitoring cycle for one SAP system/client."""
    system: str                    # e.g. "TST"
    client: str                    # e.g. "000"
    cycle_timestamp: datetime = field(default_factory=datetime.now)
    metrics: list[MetricResult] = field(default_factory=list)
    overall_status: Status = Status.UNKNOWN
    ai_analysis: Optional[AIAnalysis] = None
    errors: list[str] = field(default_factory=list)  # collector-level failures, not fatal

    def compute_overall_status(self) -> Status:
        statuses = [m.status for m in self.metrics]
        if Status.CRITICAL in statuses:
            self.overall_status = Status.CRITICAL
        elif Status.WARNING in statuses:
            self.overall_status = Status.WARNING
        elif statuses:
            self.overall_status = Status.NORMAL
        else:
            self.overall_status = Status.UNKNOWN
        return self.overall_status

    def critical_metrics(self) -> list[MetricResult]:
        return [m for m in self.metrics if m.status == Status.CRITICAL]