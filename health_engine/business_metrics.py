
from __future__ import annotations

import math
from types import ModuleType

from models.data_models import (
    MachineStatus,
    MaintenancePriority,
    ProductionImpact,
    TrendDirection,
)


def compute_downtime_risk(
    health_score: float, trend_slope: float, config: ModuleType
) -> float:
    deficit = 100.0 - health_score
    adjusted = deficit + config.DOWNTIME_TREND_FACTOR * max(0.0, -trend_slope)
    risk_raw = 100.0 / (
        1.0
        + math.exp(
            -(adjusted - config.DOWNTIME_RISK_MIDPOINT)
            / config.DOWNTIME_RISK_STEEPNESS
        )
    )
    clamped = min(
        max(risk_raw, config.DOWNTIME_RISK_MIN), config.DOWNTIME_RISK_MAX
    )
    return round(clamped, 1)


def compute_maintenance_priority(
    status: MachineStatus,
    trend: TrendDirection,
    downtime_risk_pct: float,
    config: ModuleType,
) -> MaintenancePriority:
    priority = MaintenancePriority[
        config.PRIORITY_MATRIX[status.name][trend.value]
    ]
    for level_name, threshold in config.PRIORITY_RISK_OVERRIDES.items():
        if downtime_risk_pct >= threshold:
            priority = max(priority, MaintenancePriority[level_name])
    return priority


def compute_production_impact(
    downtime_risk_pct: float, config: ModuleType
) -> ProductionImpact:
    throughput_at_risk = (
        config.NOMINAL_THROUGHPUT_UNITS_HR * downtime_risk_pct / 100.0
    )
    estimated_loss = (
        throughput_at_risk * config.UNIT_VALUE * config.IMPACT_HORIZON_HR
    )
    impact_level = config.IMPACT_LEVEL_BANDS[-1][0]
    for label, upper_bound in config.IMPACT_LEVEL_BANDS:
        if upper_bound is None or estimated_loss < upper_bound:
            impact_level = label
            break
    return ProductionImpact(
        throughput_at_risk_units_hr=throughput_at_risk,
        estimated_loss_per_day=estimated_loss,
        impact_level=impact_level,
    )
