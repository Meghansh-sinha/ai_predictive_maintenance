
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import pandas as pd

import config
from models.data_models import (
    HealthResult,
    MachineStatus,
    MaintenancePriority,
    ProductionImpact,
    SensorFlag,
    SensorReading,
    TrendDirection,
    ValidatedReading,
    ValidationFlag,
)
from utils.history import HistoryBuffer

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_reading(tick: int, *, temperature_c: float = 65.0) -> SensorReading:
    return SensorReading(
        machine_id=config.MACHINE_ID,
        timestamp=_T0 + timedelta(seconds=tick * config.TICK_INTERVAL_S),
        temperature_c=temperature_c,
        vibration_mm_s=1.8,
        pressure_bar=5.0,
        current_a=20.0,
        tick=tick,
    )


def make_validated(
    tick: int,
    *,
    is_valid: bool = True,
    flags: Tuple[SensorFlag, ...] = (),
    temperature_c: float = 65.0,
) -> ValidatedReading:
    return ValidatedReading(
        reading=make_reading(tick, temperature_c=temperature_c),
        is_valid=is_valid,
        validation_flags=flags,
        normalized={key: 0.5 for key in config.SENSOR_KEYS},
        deviation={key: 0.0 for key in config.SENSOR_KEYS},
    )


def make_result(
    tick: int,
    *,
    health_score: float = 95.0,
    status: MachineStatus = MachineStatus.HEALTHY,
) -> HealthResult:
    return HealthResult(
        machine_id=config.MACHINE_ID,
        timestamp=_T0 + timedelta(seconds=tick * config.TICK_INTERVAL_S),
        health_score=health_score,
        machine_status=status,
        confidence_score=90.0,
        trend=TrendDirection.STABLE,
        trend_slope=0.0,
        maintenance_priority=MaintenancePriority.LOW,
        downtime_risk_pct=2.0,
        production_impact=ProductionImpact(
            throughput_at_risk_units_hr=2.4,
            estimated_loss_per_day=2592.0,
            impact_level="Low",
        ),
        sensor_health={key: 100.0 for key in config.SENSOR_KEYS},
        sensor_contributions={key: 0.0 for key in config.SENSOR_KEYS},
        alerts=(),
        used_fallback_values=False,
    )


def fill(buffer: HistoryBuffer, n: int, start_tick: int = 0) -> None:
    for tick in range(start_tick, start_tick + n):
        buffer.append(make_validated(tick), make_result(tick))




def test_len_and_latest_on_empty_buffer() -> None:
    buffer = HistoryBuffer(max_len=5)
    assert len(buffer) == 0
    assert buffer.latest() is None


def test_maxlen_eviction_keeps_newest_entries() -> None:
    buffer = HistoryBuffer(max_len=3)
    fill(buffer, 5)
    assert len(buffer) == 3
    ticks = [validated.reading.tick for validated, _ in buffer.window(10)]
    assert ticks == [2, 3, 4]
    latest = buffer.latest()
    assert latest is not None
    assert latest[0].reading.tick == 4




def test_window_returns_last_n_in_chronological_order() -> None:
    buffer = HistoryBuffer(max_len=10)
    fill(buffer, 6)
    ticks = [validated.reading.tick for validated, _ in buffer.window(3)]
    assert ticks == [3, 4, 5]


def test_window_larger_than_buffer_returns_all_entries() -> None:
    buffer = HistoryBuffer(max_len=10)
    fill(buffer, 4)
    assert len(buffer.window(100)) == 4


def test_window_nonpositive_n_returns_empty_list() -> None:
    buffer = HistoryBuffer(max_len=10)
    fill(buffer, 4)
    assert buffer.window(0) == []
    assert buffer.window(-2) == []



_EXPECTED_COLUMNS = (
    ["timestamp", "tick", *config.SENSOR_KEYS, "is_valid"]
    + [f"{key}_flagged" for key in config.SENSOR_KEYS]
    + [
        "health_score",
        "machine_status",
        "confidence_score",
        "trend",
        "downtime_risk_pct",
        "maintenance_priority",
    ]
)


def test_dataframe_column_set_order_and_dtypes() -> None:
    buffer = HistoryBuffer(max_len=10)
    fill(buffer, 3)
    frame = buffer.to_dataframe()

    assert list(frame.columns) == _EXPECTED_COLUMNS
    assert str(frame["timestamp"].dtype).startswith("datetime64[ns, UTC")
    assert frame["tick"].dtype == "int64"
    for key in config.SENSOR_KEYS:
        assert frame[key].dtype == "float64"
        assert frame[f"{key}_flagged"].dtype == "bool"
    assert frame["is_valid"].dtype == "bool"
    assert frame["health_score"].dtype == "float64"
    assert frame["downtime_risk_pct"].dtype == "float64"
    assert frame["confidence_score"].dtype == "float64"
    assert frame["machine_status"].iloc[0] == "HEALTHY"
    assert frame["trend"].iloc[0] == "STABLE"
    assert frame["maintenance_priority"].iloc[0] == "LOW"


def test_dataframe_flagged_columns_reflect_sensor_flags() -> None:
    buffer = HistoryBuffer(max_len=10)
    buffer.append(make_validated(0), make_result(0))
    flagged = make_validated(
        1,
        is_valid=False,
        flags=(
            SensorFlag("temperature_c", ValidationFlag.SPIKE_DETECTED),
            SensorFlag(None, ValidationFlag.TIMESTAMP_OUT_OF_ORDER),
        ),
    )
    buffer.append(flagged, make_result(1))
    frame = buffer.to_dataframe()

    assert frame["temperature_c_flagged"].tolist() == [False, True]
    for key in ("vibration_mm_s", "pressure_bar", "current_a"):
        assert frame[f"{key}_flagged"].tolist() == [False, False]
    assert frame["is_valid"].tolist() == [True, False]


def test_empty_buffer_dataframe_has_full_schema() -> None:
    frame = HistoryBuffer(max_len=5).to_dataframe()
    assert list(frame.columns) == _EXPECTED_COLUMNS
    assert len(frame) == 0
    assert str(frame["timestamp"].dtype).startswith("datetime64[ns, UTC")
    assert frame["is_valid"].dtype == "bool"




def test_summary_aggregates_against_hand_built_data() -> None:
    buffer = HistoryBuffer(max_len=10)
    buffer.append(
        make_validated(0, temperature_c=60.0),
        make_result(0, health_score=90.0),
    )
    buffer.append(
        make_validated(1, is_valid=False, temperature_c=70.0),
        make_result(1, health_score=80.0),
    )
    buffer.append(
        make_validated(2, temperature_c=65.0),
        make_result(2, health_score=40.0, status=MachineStatus.CRITICAL),
    )

    summary = buffer.summary()

    assert summary.window_length == 3
    assert summary.start_time == make_reading(0).timestamp
    assert summary.end_time == make_reading(2).timestamp
    assert summary.health_min == 40.0
    assert summary.health_max == 90.0
    assert abs(summary.health_mean - 70.0) < 1e-9
    assert summary.health_delta == 40.0 - 90.0
    assert summary.invalid_count == 1
    assert summary.critical_count == 1
    temp_stats = summary.sensor_stats["temperature_c"]
    assert temp_stats["min"] == 60.0
    assert temp_stats["max"] == 70.0
    assert abs(temp_stats["mean"] - 65.0) < 1e-9
    assert set(summary.sensor_stats) == set(config.SENSOR_KEYS)


def test_summary_on_empty_buffer_raises_value_error() -> None:
    buffer = HistoryBuffer(max_len=5)
    try:
        buffer.summary()
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("summary() on an empty buffer must raise ValueError")


def test_summary_respects_eviction_window() -> None:
    buffer = HistoryBuffer(max_len=2)
    fill(buffer, 3)
    summary = buffer.summary()
    assert summary.window_length == 2
    assert summary.start_time == make_reading(1).timestamp
