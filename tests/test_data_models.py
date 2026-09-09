
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import config
from models.data_models import (
    AIInsight,
    HealthResult,
    HistorySummary,
    MachineStatus,
    MaintenancePriority,
    ProductionImpact,
    SensorFlag,
    SensorReading,
    SimulationScenario,
    TrendDirection,
    ValidatedReading,
    ValidationFlag,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)




def test_machine_status_is_ordered_intenum() -> None:
    assert MachineStatus.HEALTHY < MachineStatus.WARNING < MachineStatus.CRITICAL
    assert max(MachineStatus.HEALTHY, MachineStatus.CRITICAL) is MachineStatus.CRITICAL


def test_maintenance_priority_is_ordered_intenum() -> None:
    assert (
        MaintenancePriority.LOW
        < MaintenancePriority.MEDIUM
        < MaintenancePriority.HIGH
        < MaintenancePriority.URGENT
    )
    assert (
        max(MaintenancePriority.MEDIUM, MaintenancePriority.HIGH)
        is MaintenancePriority.HIGH
    )


def test_enum_member_names_match_config_string_keys() -> None:
    assert {s.name for s in SimulationScenario} == set(config.SCENARIO_NAMES)
    assert {s.name for s in MachineStatus} == set(config.STATUS_COLORS)
    assert set(config.STATUS_THRESHOLDS) <= {s.name for s in MachineStatus}
    assert {s.name for s in MachineStatus} == set(config.PRIORITY_MATRIX)
    for row in config.PRIORITY_MATRIX.values():
        assert set(row) == {t.name for t in TrendDirection}
        assert set(row.values()) <= {p.name for p in MaintenancePriority}
    assert set(config.PRIORITY_RISK_OVERRIDES) <= {
        p.name for p in MaintenancePriority
    }
    for sensor_spec in config.SENSORS.values():
        assert set(sensor_spec["drift_per_tick"]) == {
            s.name for s in SimulationScenario
        }


def test_validation_flag_members_match_spec() -> None:
    assert {f.name for f in ValidationFlag} == {
        "MISSING_FIELD",
        "OUT_OF_PHYSICAL_RANGE",
        "SPIKE_DETECTED",
        "STUCK_SIGNAL",
        "TIMESTAMP_OUT_OF_ORDER",
    }


def test_sensor_flag_supports_reading_level_none_key() -> None:
    flag = SensorFlag(None, ValidationFlag.TIMESTAMP_OUT_OF_ORDER)
    assert flag.sensor_key is None
    scoped = SensorFlag("vibration_mm_s", ValidationFlag.SPIKE_DETECTED)
    assert scoped.sensor_key in config.SENSOR_KEYS




def _reading() -> SensorReading:
    return SensorReading(
        machine_id=config.MACHINE_ID,
        timestamp=_NOW,
        temperature_c=65.0,
        vibration_mm_s=1.8,
        pressure_bar=5.0,
        current_a=20.0,
        tick=0,
    )


def test_sensor_reading_fields_and_immutability() -> None:
    reading = _reading()
    expected = {
        "machine_id",
        "timestamp",
        "temperature_c",
        "vibration_mm_s",
        "pressure_bar",
        "current_a",
        "tick",
    }
    assert {f.name for f in dataclasses.fields(reading)} == expected
    try:
        reading.temperature_c = 99.0
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("SensorReading must be frozen (§4)")


def test_sensor_reading_exposes_all_canonical_keys_as_attributes() -> None:
    reading = _reading()
    for key in config.SENSOR_KEYS:
        assert isinstance(getattr(reading, key), float)


def test_validated_reading_fields() -> None:
    validated = ValidatedReading(
        reading=_reading(),
        is_valid=True,
        validation_flags=(),
        normalized={key: 0.5 for key in config.SENSOR_KEYS},
        deviation={key: 0.0 for key in config.SENSOR_KEYS},
    )
    expected = {"reading", "is_valid", "validation_flags", "normalized", "deviation"}
    assert {f.name for f in dataclasses.fields(validated)} == expected
    try:
        validated.is_valid = False
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ValidatedReading must be frozen (§4)")


def test_health_result_fields_match_section_4_4() -> None:
    result = HealthResult(
        machine_id=config.MACHINE_ID,
        timestamp=_NOW,
        health_score=95.0,
        machine_status=MachineStatus.HEALTHY,
        confidence_score=90.0,
        trend=TrendDirection.STABLE,
        trend_slope=0.0,
        maintenance_priority=MaintenancePriority.LOW,
        downtime_risk_pct=2.0,
        production_impact=ProductionImpact(2.4, 2592.0, "Low"),
        sensor_health={key: 100.0 for key in config.SENSOR_KEYS},
        sensor_contributions={key: 0.0 for key in config.SENSOR_KEYS},
        alerts=(),
        used_fallback_values=False,
    )
    expected = {
        "machine_id",
        "timestamp",
        "health_score",
        "machine_status",
        "confidence_score",
        "trend",
        "trend_slope",
        "maintenance_priority",
        "downtime_risk_pct",
        "production_impact",
        "sensor_health",
        "sensor_contributions",
        "alerts",
        "used_fallback_values",
    }
    assert {f.name for f in dataclasses.fields(result)} == expected
    try:
        result.health_score = 10.0
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("HealthResult must be frozen (§4)")


def test_production_impact_fields_match_section_4_5() -> None:
    impact = ProductionImpact(
        throughput_at_risk_units_hr=60.0,
        estimated_loss_per_day=64800.0,
        impact_level="High",
    )
    assert {f.name for f in dataclasses.fields(impact)} == {
        "throughput_at_risk_units_hr",
        "estimated_loss_per_day",
        "impact_level",
    }


def test_ai_insight_fields_match_section_4_6() -> None:
    insight = AIInsight(
        summary="Machine healthy.",
        probable_causes=("None identified.",),
        recommended_actions=("Continue routine monitoring.",),
        urgency_note="No urgent action required.",
        model_name=config.AI_FALLBACK_MODEL_NAME,
        generated_at=_NOW,
        is_fallback=True,
        source_health_score=95.0,
    )
    expected = {
        "summary",
        "probable_causes",
        "recommended_actions",
        "urgency_note",
        "model_name",
        "generated_at",
        "is_fallback",
        "source_health_score",
    }
    assert {f.name for f in dataclasses.fields(insight)} == expected


def test_history_summary_fields_match_section_4_7() -> None:
    summary = HistorySummary(
        window_length=1,
        start_time=_NOW,
        end_time=_NOW,
        health_min=95.0,
        health_mean=95.0,
        health_max=95.0,
        health_delta=0.0,
        sensor_stats={
            key: {"min": 0.0, "mean": 0.0, "max": 0.0} for key in config.SENSOR_KEYS
        },
        invalid_count=0,
        critical_count=0,
    )
    expected = {
        "window_length",
        "start_time",
        "end_time",
        "health_min",
        "health_mean",
        "health_max",
        "health_delta",
        "sensor_stats",
        "invalid_count",
        "critical_count",
    }
    assert {f.name for f in dataclasses.fields(summary)} == expected
