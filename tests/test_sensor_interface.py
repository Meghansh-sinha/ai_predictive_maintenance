
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from models.data_models import SensorReading, ValidationFlag
from sensor_interface import SensorInterface
from utils.exceptions import SensorValidationError

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_NOMINAL = {
    "temperature_c": 65.0,
    "vibration_mm_s": 1.8,
    "pressure_bar": 5.0,
    "current_a": 20.0,
}


def make_reading(
    tick: int,
    *,
    timestamp: Optional[datetime] = None,
    **overrides: float,
) -> SensorReading:
    values = {**_NOMINAL, **overrides}
    return SensorReading(
        machine_id=config.MACHINE_ID,
        timestamp=timestamp
        or (_T0 + timedelta(seconds=tick * config.TICK_INTERVAL_S)),
        temperature_c=values["temperature_c"],
        vibration_mm_s=values["vibration_mm_s"],
        pressure_bar=values["pressure_bar"],
        current_a=values["current_a"],
        tick=tick,
    )


def flags_of(validated, flag: ValidationFlag, sensor_key: Optional[str] = None):
    return [
        f
        for f in validated.validation_flags
        if f.flag is flag and (sensor_key is None or f.sensor_key == sensor_key)
    ]




def test_nominal_reading_is_valid_with_no_flags() -> None:
    interface = SensorInterface(config)
    validated = interface.process(make_reading(0))
    assert validated.is_valid
    assert validated.validation_flags == ()
    assert set(validated.normalized) == set(config.SENSOR_KEYS)
    assert set(validated.deviation) == set(config.SENSOR_KEYS)
    assert all(validated.deviation[key] == 0.0 for key in config.SENSOR_KEYS)


def test_process_does_not_mutate_input_reading() -> None:
    interface = SensorInterface(config)
    reading = make_reading(0)
    snapshot = dataclasses.asdict(reading)
    interface.process(reading)
    assert dataclasses.asdict(reading) == snapshot




def test_missing_field_raises_sensor_validation_error() -> None:
    interface = SensorInterface(config)
    reading = make_reading(0)
    object.__setattr__(reading, "temperature_c", None)
    try:
        interface.process(reading)
    except SensorValidationError as exc:
        assert "temperature_c" in str(exc)
    else:
        raise AssertionError("missing field must raise SensorValidationError")


def test_non_numeric_field_raises_sensor_validation_error() -> None:
    interface = SensorInterface(config)
    reading = make_reading(0)
    object.__setattr__(reading, "pressure_bar", "not-a-number")
    try:
        interface.process(reading)
    except SensorValidationError as exc:
        assert "pressure_bar" in str(exc)
    else:
        raise AssertionError("non-numeric field must raise SensorValidationError")


def test_structural_check_passes_for_all_numeric_fields() -> None:
    interface = SensorInterface(config)
    assert interface.process(make_reading(0)).is_valid




def test_out_of_physical_range_triggers_above_and_below() -> None:
    interface = SensorInterface(config)
    p_lo, p_hi = config.SENSORS["temperature_c"]["plausible_range"]
    validated = interface.process(make_reading(0, temperature_c=p_hi + 1.0))
    assert flags_of(validated, ValidationFlag.OUT_OF_PHYSICAL_RANGE, "temperature_c")
    assert not validated.is_valid

    interface = SensorInterface(config)
    validated = interface.process(make_reading(0, temperature_c=p_lo - 1.0))
    assert flags_of(validated, ValidationFlag.OUT_OF_PHYSICAL_RANGE, "temperature_c")


def test_out_of_physical_range_boundary_values_do_not_trigger() -> None:
    p_lo, p_hi = config.SENSORS["pressure_bar"]["plausible_range"]
    for boundary in (p_lo, p_hi):
        interface = SensorInterface(config)
        validated = interface.process(make_reading(0, pressure_bar=boundary))
        assert not flags_of(
            validated, ValidationFlag.OUT_OF_PHYSICAL_RANGE, "pressure_bar"
        )




def test_spike_triggers_beyond_delta_limit_and_first_reading_skips() -> None:
    interface = SensorInterface(config)
    limit = config.SPIKE_DELTA_LIMIT["vibration_mm_s"]
    first = interface.process(make_reading(0, vibration_mm_s=1.8 + 2 * limit))
    assert not flags_of(first, ValidationFlag.SPIKE_DETECTED, "vibration_mm_s")
    interface = SensorInterface(config)
    interface.process(make_reading(0))
    spiked = interface.process(
        make_reading(1, vibration_mm_s=_NOMINAL["vibration_mm_s"] + limit + 0.01)
    )
    assert flags_of(spiked, ValidationFlag.SPIKE_DETECTED, "vibration_mm_s")
    assert not spiked.is_valid


def test_spike_boundary_delta_exactly_at_limit_does_not_trigger() -> None:
    interface = SensorInterface(config)
    limit = config.SPIKE_DELTA_LIMIT["current_a"]
    interface.process(make_reading(0))
    boundary = interface.process(
        make_reading(1, current_a=_NOMINAL["current_a"] + limit)
    )
    assert not flags_of(boundary, ValidationFlag.SPIKE_DETECTED, "current_a")


def test_spike_recovery_tick_is_not_double_flagged() -> None:
    interface = SensorInterface(config)
    limit = config.SPIKE_DELTA_LIMIT["vibration_mm_s"]
    interface.process(make_reading(0))
    interface.process(make_reading(1, vibration_mm_s=1.8 + limit + 0.5))
    recovery = interface.process(make_reading(2))
    assert not flags_of(recovery, ValidationFlag.SPIKE_DETECTED, "vibration_mm_s")
    assert recovery.is_valid


def test_out_of_range_value_does_not_become_spike_baseline() -> None:
    interface = SensorInterface(config)
    interface.process(make_reading(0))
    p_lo, _ = config.SENSORS["pressure_bar"]["plausible_range"]
    interface.process(make_reading(1, pressure_bar=p_lo - 1.0))
    back = interface.process(make_reading(2))
    assert not flags_of(back, ValidationFlag.SPIKE_DETECTED, "pressure_bar")




def test_stuck_signal_triggers_at_limit_and_not_before() -> None:
    interface = SensorInterface(config)
    limit = config.STUCK_TICK_LIMIT
    epsilon = config.STUCK_EPSILON["pressure_bar"]
    last = None
    for tick in range(limit):
        jitter = (0.4 * epsilon) if tick % 2 else -(0.4 * epsilon)
        last = interface.process(
            make_reading(tick, pressure_bar=5.0 + jitter)
        )
        if tick < limit - 1:
            assert not flags_of(last, ValidationFlag.STUCK_SIGNAL, "pressure_bar"), (
                f"stuck flag must not trigger at run length {tick + 1}"
            )
    assert last is not None
    assert flags_of(last, ValidationFlag.STUCK_SIGNAL, "pressure_bar")


def test_stuck_run_resets_when_value_moves_beyond_epsilon() -> None:
    interface = SensorInterface(config)
    limit = config.STUCK_TICK_LIMIT
    epsilon = config.STUCK_EPSILON["current_a"]
    for tick in range(limit - 1):
        interface.process(make_reading(tick, current_a=20.0))
    moved = interface.process(
        make_reading(limit - 1, current_a=20.0 + 3.0 * epsilon)
    )
    assert not flags_of(moved, ValidationFlag.STUCK_SIGNAL, "current_a")
    for tick in range(limit, limit + limit - 2):
        result = interface.process(
            make_reading(tick, current_a=20.0 + 3.0 * epsilon)
        )
        assert not flags_of(result, ValidationFlag.STUCK_SIGNAL, "current_a")




def test_timestamp_out_of_order_triggers_and_is_reading_level() -> None:
    interface = SensorInterface(config)
    interface.process(make_reading(0, timestamp=_T0))
    stale = interface.process(make_reading(1, timestamp=_T0))
    flags = flags_of(stale, ValidationFlag.TIMESTAMP_OUT_OF_ORDER)
    assert flags and flags[0].sensor_key is None
    assert not stale.is_valid


def test_strictly_increasing_timestamps_do_not_trigger() -> None:
    interface = SensorInterface(config)
    interface.process(make_reading(0, timestamp=_T0))
    later = interface.process(
        make_reading(1, timestamp=_T0 + timedelta(microseconds=1))
    )
    assert not flags_of(later, ValidationFlag.TIMESTAMP_OUT_OF_ORDER)


def test_out_of_order_reading_does_not_lower_timestamp_baseline() -> None:
    interface = SensorInterface(config)
    interface.process(make_reading(0, timestamp=_T0 + timedelta(seconds=10)))
    interface.process(make_reading(1, timestamp=_T0))
    still_stale = interface.process(
        make_reading(2, timestamp=_T0 + timedelta(seconds=5))
    )
    assert flags_of(still_stale, ValidationFlag.TIMESTAMP_OUT_OF_ORDER)




def test_multiple_simultaneous_flags_are_all_recorded() -> None:
    interface = SensorInterface(config)
    interface.process(make_reading(0, timestamp=_T0))
    _, p_hi = config.SENSORS["temperature_c"]["plausible_range"]
    combined = interface.process(
        make_reading(1, timestamp=_T0, temperature_c=p_hi + 5.0)
    )
    assert flags_of(combined, ValidationFlag.OUT_OF_PHYSICAL_RANGE, "temperature_c")
    assert flags_of(combined, ValidationFlag.SPIKE_DETECTED, "temperature_c")
    assert flags_of(combined, ValidationFlag.TIMESTAMP_OUT_OF_ORDER)
    assert not combined.is_valid
    assert len(combined.validation_flags) == 3




def _deviation_for(interface_value: float, key: str = "temperature_c") -> float:
    interface = SensorInterface(config)
    validated = interface.process(make_reading(0, **{key: interface_value}))
    return validated.deviation[key]


def test_deviation_zero_inside_band_and_at_band_edge() -> None:
    n_lo, n_hi = config.SENSORS["temperature_c"]["nominal_band"]
    assert _deviation_for((n_lo + n_hi) / 2.0) == 0.0
    assert _deviation_for(n_hi) == 0.0


def test_deviation_half_way_to_critical_is_exactly_0_5() -> None:
    spec = config.SENSORS["temperature_c"]
    _, n_hi = spec["nominal_band"]
    c_hi = spec["critical_high"]
    assert abs(_deviation_for((n_hi + c_hi) / 2.0) - 0.5) < 1e-12


def test_deviation_at_and_beyond_critical_is_exactly_1_0() -> None:
    spec = config.SENSORS["temperature_c"]
    c_hi = spec["critical_high"]
    assert _deviation_for(c_hi) == 1.0
    assert _deviation_for(c_hi + 10.0) == 1.0


def test_deviation_below_band_uses_low_side_critical_symmetrically() -> None:
    spec = config.SENSORS["temperature_c"]
    n_lo, _ = spec["nominal_band"]
    c_lo = spec["critical_low"]
    midpoint = (n_lo + c_lo) / 2.0
    assert abs(_deviation_for(midpoint) - 0.5) < 1e-12
    assert _deviation_for(c_lo) == 1.0


def test_deviation_is_zero_on_side_without_critical_bound() -> None:
    n_lo, _ = config.SENSORS["vibration_mm_s"]["nominal_band"]
    assert _deviation_for(n_lo - 0.5, key="vibration_mm_s") == 0.0
    assert _deviation_for(0.1, key="vibration_mm_s") == 0.0




def test_normalization_maps_plausible_range_to_unit_interval() -> None:
    p_lo, p_hi = config.SENSORS["current_a"]["plausible_range"]
    interface = SensorInterface(config)
    validated = interface.process(make_reading(0, current_a=p_lo))
    assert validated.normalized["current_a"] == 0.0
    interface = SensorInterface(config)
    validated = interface.process(
        make_reading(0, current_a=(p_lo + p_hi) / 2.0)
    )
    assert abs(validated.normalized["current_a"] - 0.5) < 1e-12


def test_normalization_clamps_outside_plausible_range() -> None:
    p_lo, p_hi = config.SENSORS["current_a"]["plausible_range"]
    interface = SensorInterface(config)
    validated = interface.process(make_reading(0, current_a=p_hi + 10.0))
    assert validated.normalized["current_a"] == 1.0
    interface = SensorInterface(config)
    validated = interface.process(make_reading(0, current_a=p_lo - 10.0))
    assert validated.normalized["current_a"] == 0.0


def test_normalized_and_deviation_populated_even_when_invalid() -> None:
    interface = SensorInterface(config)
    _, p_hi = config.SENSORS["temperature_c"]["plausible_range"]
    validated = interface.process(make_reading(0, temperature_c=p_hi + 5.0))
    assert not validated.is_valid
    assert set(validated.normalized) == set(config.SENSOR_KEYS)
    assert set(validated.deviation) == set(config.SENSOR_KEYS)
    assert validated.normalized["temperature_c"] == 1.0
    assert validated.deviation["temperature_c"] == 1.0
