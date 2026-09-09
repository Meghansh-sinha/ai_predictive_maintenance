
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import config
from health_engine import HealthAnalysisEngine
from models.data_models import (
    MachineStatus,
    MaintenancePriority,
    SensorFlag,
    SensorReading,
    TrendDirection,
    ValidatedReading,
    ValidationFlag,
)
from utils.exceptions import AnalysisError, ConfigurationError
from utils.history import HistoryBuffer

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_NOMINAL = {
    "temperature_c": 65.0,
    "vibration_mm_s": 1.8,
    "pressure_bar": 5.0,
    "current_a": 20.0,
}


def make_validated(
    tick: int,
    *,
    deviation: Optional[Dict[str, float]] = None,
    is_valid: bool = True,
    flags: Tuple[SensorFlag, ...] = (),
    values: Optional[Dict[str, float]] = None,
) -> ValidatedReading:
    raw = {**_NOMINAL, **(values or {})}
    reading = SensorReading(
        machine_id=config.MACHINE_ID,
        timestamp=_T0 + timedelta(seconds=tick * config.TICK_INTERVAL_S),
        temperature_c=raw["temperature_c"],
        vibration_mm_s=raw["vibration_mm_s"],
        pressure_bar=raw["pressure_bar"],
        current_a=raw["current_a"],
        tick=tick,
    )
    devs = {key: 0.0 for key in config.SENSOR_KEYS}
    devs.update(deviation or {})
    return ValidatedReading(
        reading=reading,
        is_valid=is_valid,
        validation_flags=flags,
        normalized={key: 0.5 for key in config.SENSOR_KEYS},
        deviation=devs,
    )


def prefill_history(
    engine: HealthAnalysisEngine,
    scores_devs: list,
    start_tick: int = 0,
) -> HistoryBuffer:
    history = HistoryBuffer(max_len=config.HISTORY_MAX_LEN)
    for offset, dev in enumerate(scores_devs):
        validated = make_validated(
            start_tick + offset, deviation={"temperature_c": dev}
        )
        result = engine.analyze(validated, history)
        history.append(validated, result)
    return history




def test_golden_score_hand_computed() -> None:
    engine = HealthAnalysisEngine(config)
    history = HistoryBuffer(max_len=10)
    result = engine.analyze(
        make_validated(0, deviation={"temperature_c": 0.5}), history
    )

    assert result.health_score == 85.0
    assert result.machine_status is MachineStatus.HEALTHY
    assert result.trend is TrendDirection.STABLE
    assert result.trend_slope == 0.0
    assert abs(result.sensor_health["temperature_c"] - 50.0) < 1e-9
    assert abs(result.sensor_contributions["temperature_c"] - 15.0) < 1e-9
    assert "trend_penalty" not in result.sensor_contributions
    assert abs(sum(result.sensor_contributions.values()) - 15.0) < 1e-9
    assert result.downtime_risk_pct == 3.4
    assert result.maintenance_priority is MaintenancePriority.LOW
    assert result.production_impact.impact_level == "Low"
    assert result.machine_id == config.MACHINE_ID
    assert result.timestamp == make_validated(0).reading.timestamp
    assert result.used_fallback_values is False
    assert result.alerts == ()


def test_perfect_reading_scores_100_with_zero_contributions() -> None:
    engine = HealthAnalysisEngine(config)
    result = engine.analyze(make_validated(0), HistoryBuffer(max_len=10))
    assert result.health_score == 100.0
    assert abs(sum(result.sensor_contributions.values())) < 1e-9




def _config_stub(**overrides: object) -> SimpleNamespace:
    attrs = {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper()
    }
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def test_bad_weight_sum_raises_configuration_error() -> None:
    broken = _config_stub(
        SENSOR_WEIGHTS={
            "vibration_mm_s": 0.5,
            "temperature_c": 0.3,
            "pressure_bar": 0.2,
            "current_a": 0.2,
        }
    )
    try:
        HealthAnalysisEngine(broken)
    except ConfigurationError as exc:
        assert "sum" in str(exc)
    else:
        raise AssertionError("bad weight sum must raise ConfigurationError")


def test_missing_weight_key_raises_configuration_error() -> None:
    broken = _config_stub(
        SENSOR_WEIGHTS={"vibration_mm_s": 0.5, "temperature_c": 0.5}
    )
    try:
        HealthAnalysisEngine(broken)
    except ConfigurationError as exc:
        assert "SENSOR_KEYS" in str(exc)
    else:
        raise AssertionError("missing weight keys must raise ConfigurationError")




def test_missing_deviation_sensor_raises_analysis_error() -> None:
    engine = HealthAnalysisEngine(config)
    validated = make_validated(0)
    broken = ValidatedReading(
        reading=validated.reading,
        is_valid=True,
        validation_flags=(),
        normalized=validated.normalized,
        deviation={"temperature_c": 0.0},
    )
    try:
        engine.analyze(broken, HistoryBuffer(max_len=10))
    except AnalysisError as exc:
        assert "deviation" in str(exc)
    else:
        raise AssertionError("missing sensors must raise AnalysisError")




def _dev_for_score(target_score: float) -> float:
    return (100.0 - target_score) / (
        100.0 * config.SENSOR_WEIGHTS["temperature_c"]
    )


def test_score_81_after_warning_stays_warning() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [_dev_for_score(75.0)] * 6)
    assert history.latest()[1].machine_status is MachineStatus.WARNING

    validated = make_validated(6, deviation={"temperature_c": _dev_for_score(81.0)})
    result = engine.analyze(validated, history)
    assert result.health_score == 81.0
    assert result.machine_status is MachineStatus.WARNING


def test_score_84_after_warning_promotes_to_healthy() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [_dev_for_score(75.0)] * 6)
    validated = make_validated(6, deviation={"temperature_c": _dev_for_score(84.0)})
    result = engine.analyze(validated, history)
    assert result.health_score == 84.0
    assert result.machine_status is MachineStatus.HEALTHY


def test_demotion_applies_immediately() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [0.0] * 6)
    validated = make_validated(6, deviation={"temperature_c": _dev_for_score(54.0)})
    result = engine.analyze(validated, history)
    assert result.machine_status is MachineStatus.CRITICAL
    assert any("Status changed" in alert for alert in result.alerts)


def test_critical_to_warning_requires_hysteresis_clearance() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [_dev_for_score(40.0)] * 6)
    borderline = engine.analyze(
        make_validated(6, deviation={"temperature_c": _dev_for_score(56.0)}),
        history,
    )
    assert borderline.machine_status is MachineStatus.CRITICAL
    cleared = engine.analyze(
        make_validated(6, deviation={"temperature_c": _dev_for_score(58.0)}),
        history,
    )
    assert cleared.machine_status is MachineStatus.WARNING




def _history_with_linear_scores(
    engine: HealthAnalysisEngine, start: float, slope: float, n: int
) -> HistoryBuffer:
    devs = [_dev_for_score(start + slope * i) for i in range(n)]
    return prefill_history(engine, devs)


def test_trend_degrading_at_and_beyond_threshold() -> None:
    engine = HealthAnalysisEngine(config)
    history = _history_with_linear_scores(engine, 95.0, -0.2, 10)
    result = engine.analyze(make_validated(10), history)
    assert result.trend is TrendDirection.DEGRADING
    assert result.trend_slope < config.TREND_DEGRADING_SLOPE + 0.06


def test_trend_stable_inside_thresholds() -> None:
    engine = HealthAnalysisEngine(config)
    history = _history_with_linear_scores(engine, 95.0, -0.1, 10)
    result = engine.analyze(make_validated(10), history)
    assert result.trend is TrendDirection.STABLE


def test_trend_improving_beyond_threshold() -> None:
    engine = HealthAnalysisEngine(config)
    history = _history_with_linear_scores(engine, 60.0, +0.2, 10)
    result = engine.analyze(
        make_validated(10, deviation={"temperature_c": _dev_for_score(62.0)}),
        history,
    )
    assert result.trend is TrendDirection.IMPROVING


def test_trend_stable_below_min_points() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [_dev_for_score(90.0)] * (
        config.TREND_MIN_POINTS - 1
    ))
    result = engine.analyze(make_validated(4), history)
    assert result.trend is TrendDirection.STABLE
    assert result.trend_slope == 0.0




def test_degrading_trend_applies_capped_penalty_and_invariant_holds() -> None:
    engine = HealthAnalysisEngine(config)
    history = _history_with_linear_scores(engine, 95.0, -0.4, 10)
    current_dev = _dev_for_score(91.0)
    result = engine.analyze(
        make_validated(10, deviation={"temperature_c": current_dev}), history
    )
    assert result.trend is TrendDirection.DEGRADING
    penalty = result.sensor_contributions["trend_penalty"]
    expected_penalty = min(
        config.TREND_PENALTY_CAP,
        abs(result.trend_slope) * config.TREND_PENALTY_MULTIPLIER,
    )
    assert abs(penalty - expected_penalty) < 1e-9
    total = sum(result.sensor_contributions.values())
    assert abs((100.0 - total) - result.health_score) <= 0.05 + 1e-9
    assert result.health_score == round(100.0 - total, 1)




def test_invalid_reading_uses_last_known_good_and_caps_confidence() -> None:
    engine = HealthAnalysisEngine(config)
    known_dev = 0.2
    history = prefill_history(engine, [known_dev] * 6)

    flagged = make_validated(
        6,
        deviation={"temperature_c": 1.0},
        is_valid=False,
        flags=(SensorFlag("temperature_c", ValidationFlag.SPIKE_DETECTED),),
    )
    result = engine.analyze(flagged, history)

    assert result.used_fallback_values is True
    assert result.health_score == 94.0
    assert result.confidence_score <= config.FALLBACK_CONFIDENCE_CAP
    assert any("substituted last-known-good" in a for a in result.alerts)
    assert any("SPIKE_DETECTED" in a for a in result.alerts)


def test_invalid_reading_with_empty_history_uses_nominal_midpoint() -> None:
    engine = HealthAnalysisEngine(config)
    flagged = make_validated(
        0,
        deviation={"vibration_mm_s": 1.0},
        is_valid=False,
        flags=(SensorFlag("vibration_mm_s", ValidationFlag.OUT_OF_PHYSICAL_RANGE),),
    )
    result = engine.analyze(flagged, HistoryBuffer(max_len=10))
    assert result.health_score == 100.0
    assert result.used_fallback_values is True


def test_reading_level_flag_marks_fallback_without_substitution() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [0.0] * 3)
    flagged = make_validated(
        3,
        is_valid=False,
        flags=(SensorFlag(None, ValidationFlag.TIMESTAMP_OUT_OF_ORDER),),
    )
    result = engine.analyze(flagged, history)
    assert result.used_fallback_values is True
    assert result.confidence_score <= config.FALLBACK_CONFIDENCE_CAP
    assert any("TIMESTAMP_OUT_OF_ORDER" in a for a in result.alerts)


def test_pipeline_never_emits_a_gap_for_invalid_readings() -> None:
    engine = HealthAnalysisEngine(config)
    flagged = make_validated(
        0,
        is_valid=False,
        flags=(SensorFlag("current_a", ValidationFlag.STUCK_SIGNAL),),
    )
    result = engine.analyze(flagged, HistoryBuffer(max_len=10))
    assert set(result.sensor_health) == set(config.SENSOR_KEYS)
    assert result.production_impact is not None




def test_identical_inputs_produce_identical_outputs() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [0.1, 0.15, 0.2, 0.25, 0.3, 0.35])
    validated = make_validated(6, deviation={"temperature_c": 0.4})
    first = engine.analyze(validated, history)
    second = engine.analyze(validated, history)
    assert first == second


def test_analyze_does_not_mutate_history() -> None:
    engine = HealthAnalysisEngine(config)
    history = prefill_history(engine, [0.1] * 5)
    before = len(history)
    engine.analyze(make_validated(5), history)
    assert len(history) == before
