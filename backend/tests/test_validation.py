"""Unit tests for historical validation engine."""
from pathlib import Path
import pandas as pd

from app.services.physical_risk import PhysicalRiskModel
from app.services.validation import HistoricalValidator


def test_zero_negative_samples_reports_unavailable_metrics():
    validator = HistoricalValidator()
    metrics = validator.evaluate_model()

    assert metrics.eligible_negative_samples == 0
    assert metrics.precision is None
    assert metrics.false_alarm_rate is None
    assert metrics.f1_score is None
    assert metrics.unavailability_reason is not None
    assert "Zero verified negative control samples" in metrics.unavailability_reason


def test_unknown_labels_are_excluded_from_supervised_metrics():
    validator = HistoricalValidator()
    metrics = validator.evaluate_model()

    assert metrics.excluded_unknown_samples > 3000
    assert metrics.eligible_positive_samples == 42


def test_lead_time_calculated_for_detected_events():
    validator = HistoricalValidator()
    # At sensitivity threshold (0.10), major storms are detected
    metrics = validator.evaluate_model(alert_threshold=0.10, temporal_lead_window_h=24)

    assert metrics.detected_events > 0
    assert metrics.detected_incidents > 0
    assert metrics.median_lead_time_min is not None
    assert metrics.median_lead_time_min >= 0.0


def test_event_based_grouping_evaluation():
    validator = HistoricalValidator()
    metrics = validator.evaluate_model(alert_threshold=0.10, temporal_lead_window_h=24)

    assert metrics.total_events == 6
    assert 0.0 <= metrics.event_recall <= 1.0
    assert 0.0 <= metrics.incident_recall <= 1.0
    assert len(metrics.incident_details) == metrics.total_incidents

