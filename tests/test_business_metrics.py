
from __future__ import annotations

import config
from health_engine.business_metrics import (
    compute_downtime_risk,
    compute_maintenance_priority,
    compute_production_impact,
)
from models.data_models import (
    MachineStatus,
    MaintenancePriority,
    TrendDirection,
)



def test_risk_is_monotonic_in_health_deficit() -> None:
    risks = [
        compute_downtime_risk(score, 0.0, config)
        for score in range(100, -1, -5)
    ]
    assert risks == sorted(risks)


def test_risk_anchor_healthy_stable_machine() -> None:
    risk = compute_downtime_risk(95.0, 0.0, config)
    assert config.DOWNTIME_RISK_MIN <= risk <= 3.0


def test_risk_anchor_score_55_stable_is_50_percent() -> None:
    assert compute_downtime_risk(55.0, 0.0, config) == 50.0


def test_risk_anchor_score_30_rapidly_degrading_exceeds_90() -> None:
    assert compute_downtime_risk(30.0, -0.6, config) > 90.0


def test_degrading_trend_inflates_risk_and_improving_does_not() -> None:
    stable = compute_downtime_risk(70.0, 0.0, config)
    degrading = compute_downtime_risk(70.0, -0.5, config)
    improving = compute_downtime_risk(70.0, +0.5, config)
    assert degrading > stable
    assert improving == stable


def test_risk_is_clamped_to_configured_bounds() -> None:
    assert compute_downtime_risk(100.0, 0.0, config) >= config.DOWNTIME_RISK_MIN
    assert compute_downtime_risk(0.0, -5.0, config) <= config.DOWNTIME_RISK_MAX



_LOW_RISK = 10.0

_EXPECTED_MATRIX = {
    (MachineStatus.HEALTHY, TrendDirection.IMPROVING): MaintenancePriority.LOW,
    (MachineStatus.HEALTHY, TrendDirection.STABLE): MaintenancePriority.LOW,
    (MachineStatus.HEALTHY, TrendDirection.DEGRADING): MaintenancePriority.MEDIUM,
    (MachineStatus.WARNING, TrendDirection.IMPROVING): MaintenancePriority.MEDIUM,
    (MachineStatus.WARNING, TrendDirection.STABLE): MaintenancePriority.MEDIUM,
    (MachineStatus.WARNING, TrendDirection.DEGRADING): MaintenancePriority.HIGH,
    (MachineStatus.CRITICAL, TrendDirection.IMPROVING): MaintenancePriority.HIGH,
    (MachineStatus.CRITICAL, TrendDirection.STABLE): MaintenancePriority.URGENT,
    (MachineStatus.CRITICAL, TrendDirection.DEGRADING): MaintenancePriority.URGENT,
}


def test_full_priority_matrix_all_nine_cells() -> None:
    for (status, trend), expected in _EXPECTED_MATRIX.items():
        actual = compute_maintenance_priority(status, trend, _LOW_RISK, config)
        assert actual is expected, (status.name, trend.value)


def test_risk_override_at_least_high_at_65() -> None:
    threshold = config.PRIORITY_RISK_OVERRIDES["HIGH"]
    result = compute_maintenance_priority(
        MachineStatus.HEALTHY, TrendDirection.STABLE, threshold, config
    )
    assert result is MaintenancePriority.HIGH
    below = compute_maintenance_priority(
        MachineStatus.HEALTHY, TrendDirection.STABLE, threshold - 0.1, config
    )
    assert below is MaintenancePriority.LOW


def test_risk_override_at_least_urgent_at_85() -> None:
    threshold = config.PRIORITY_RISK_OVERRIDES["URGENT"]
    result = compute_maintenance_priority(
        MachineStatus.HEALTHY, TrendDirection.STABLE, threshold, config
    )
    assert result is MaintenancePriority.URGENT


def test_override_never_lowers_a_higher_matrix_priority() -> None:
    result = compute_maintenance_priority(
        MachineStatus.CRITICAL,
        TrendDirection.STABLE,
        config.PRIORITY_RISK_OVERRIDES["HIGH"],
        config,
    )
    assert result is MaintenancePriority.URGENT




def test_production_impact_arithmetic() -> None:
    impact = compute_production_impact(50.0, config)
    expected_throughput = config.NOMINAL_THROUGHPUT_UNITS_HR * 0.5
    assert abs(impact.throughput_at_risk_units_hr - expected_throughput) < 1e-9
    expected_loss = (
        expected_throughput * config.UNIT_VALUE * config.IMPACT_HORIZON_HR
    )
    assert abs(impact.estimated_loss_per_day - expected_loss) < 1e-9


def test_impact_banding_boundaries() -> None:
    bands = dict(
        (label, upper) for label, upper in config.IMPACT_LEVEL_BANDS
    )
    unit_loss_per_pct = (
        config.NOMINAL_THROUGHPUT_UNITS_HR
        / 100.0
        * config.UNIT_VALUE
        * config.IMPACT_HORIZON_HR
    )

    def pct_for_loss(loss: float) -> float:
        return loss / unit_loss_per_pct

    just_below_low = compute_production_impact(
        pct_for_loss(bands["Low"] - 1.0), config
    )
    assert just_below_low.impact_level == "Low"
    at_low_bound = compute_production_impact(pct_for_loss(bands["Low"]), config)
    assert at_low_bound.impact_level == "Moderate"
    high = compute_production_impact(pct_for_loss(bands["Moderate"]), config)
    assert high.impact_level == "High"
    severe = compute_production_impact(pct_for_loss(bands["High"]), config)
    assert severe.impact_level == "Severe"


def test_zero_and_full_risk_edge_cases() -> None:
    minimal = compute_production_impact(config.DOWNTIME_RISK_MIN, config)
    assert minimal.impact_level == "Low"
    assert minimal.throughput_at_risk_units_hr > 0.0
    maximal = compute_production_impact(config.DOWNTIME_RISK_MAX, config)
    assert maximal.impact_level == "Severe"
