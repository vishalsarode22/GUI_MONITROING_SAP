"""
Evaluates MetricResult objects against configured thresholds.
Does NOT collect data -- only classifies already-collected numeric metrics
into NORMAL / WARNING / CRITICAL.

Metrics that already carry a status (e.g. SAP process GREEN/RED from
sapcontrol) are left untouched -- this engine only overrides UNKNOWN status
for metrics that have a matching threshold definition.
"""

from core.models import MetricResult, Status
from utils.logger import get_logger

log = get_logger(__name__, "monitoring")


def _threshold_key_for_metric(metric_name: str) -> str | None:
    """
    Maps a metric name to its threshold config key.
    Disk metrics are named like 'disk_/', 'disk_/usr/sap' -- all map to 'disk'.
    """
    if metric_name.startswith("disk_"):
        return "disk"
    return metric_name  # cpu, memory, swap, load_1m match directly


def evaluate_metric(metric: MetricResult, thresholds: dict) -> MetricResult:
    """
    Returns a new status for the metric based on thresholds.
    Only applies to metrics with status == UNKNOWN and a numeric value.
    Metrics already classified (e.g. SAP process status) pass through unchanged.
    """
    if metric.status != Status.UNKNOWN:
        return metric  # already classified by its own collector (e.g. sapcontrol)

    if metric.value is None:
        log.debug(f"Metric '{metric.name}' has no numeric value -- leaving UNKNOWN.")
        return metric

    key = _threshold_key_for_metric(metric.name)
    limits = thresholds.get(key)
    if not limits:
        log.debug(f"No threshold configured for metric '{metric.name}' (key='{key}') -- leaving UNKNOWN.")
        return metric

    warning = limits.get("warning")
    critical = limits.get("critical")

    if critical is not None and metric.value >= critical:
        metric.status = Status.CRITICAL
    elif warning is not None and metric.value >= warning:
        metric.status = Status.WARNING
    else:
        metric.status = Status.NORMAL

    metric.threshold_warning = warning
    metric.threshold_critical = critical

    return metric


def evaluate_all(metrics: list[MetricResult], thresholds: dict) -> list[MetricResult]:
    return [evaluate_metric(m, thresholds) for m in metrics]