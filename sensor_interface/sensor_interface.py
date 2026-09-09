
from __future__ import annotations

from datetime import datetime
from types import ModuleType
from typing import Dict, List, Optional, Tuple

from models.data_models import (
    SensorFlag,
    SensorReading,
    ValidatedReading,
    ValidationFlag,
)
from utils.exceptions import SensorValidationError
from utils.logger import get_logger


class SensorInterface:

    def __init__(self, config: ModuleType) -> None:
        self._config = config
        self._logger = get_logger(__name__)
        self._spike_baseline: Dict[str, Optional[float]] = {
            key: None for key in config.SENSOR_KEYS
        }
        self._stuck_reference: Dict[str, Optional[float]] = {
            key: None for key in config.SENSOR_KEYS
        }
        self._stuck_run_length: Dict[str, int] = {
            key: 0 for key in config.SENSOR_KEYS
        }
        self._last_timestamp: Optional[datetime] = None


    def process(self, reading: SensorReading) -> ValidatedReading:
        values = self._check_structure(reading)
        flags: List[SensorFlag] = []

        out_of_range: Dict[str, bool] = {}
        for key in self._config.SENSOR_KEYS:
            p_lo, p_hi = self._config.SENSORS[key]["plausible_range"]
            out_of_range[key] = values[key] < p_lo or values[key] > p_hi
            if out_of_range[key]:
                flags.append(SensorFlag(key, ValidationFlag.OUT_OF_PHYSICAL_RANGE))

        spiked: Dict[str, bool] = {}
        for key in self._config.SENSOR_KEYS:
            baseline = self._spike_baseline[key]
            spiked[key] = (
                baseline is not None
                and abs(values[key] - baseline)
                > self._config.SPIKE_DELTA_LIMIT[key]
            )
            if spiked[key]:
                flags.append(SensorFlag(key, ValidationFlag.SPIKE_DETECTED))

        for key in self._config.SENSOR_KEYS:
            if self._update_stuck_run(key, values[key]):
                flags.append(SensorFlag(key, ValidationFlag.STUCK_SIGNAL))

        if (
            self._last_timestamp is not None
            and reading.timestamp <= self._last_timestamp
        ):
            flags.append(SensorFlag(None, ValidationFlag.TIMESTAMP_OUT_OF_ORDER))

        self._log_flags(reading, values, flags)
        self._advance_state(reading, values, out_of_range, spiked)

        return ValidatedReading(
            reading=reading,
            is_valid=not flags,
            validation_flags=tuple(flags),
            normalized={
                key: self._normalize(key, values[key])
                for key in self._config.SENSOR_KEYS
            },
            deviation={
                key: self._deviation(key, values[key])
                for key in self._config.SENSOR_KEYS
            },
        )


    def _check_structure(self, reading: SensorReading) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for key in self._config.SENSOR_KEYS:
            raw = getattr(reading, key, None)
            if raw is None:
                raise SensorValidationError(
                    f"Sensor reading is structurally invalid: field {key!r} "
                    "is missing or None. This indicates a programming error "
                    "in the upstream producer."
                )
            try:
                values[key] = float(raw)
            except (TypeError, ValueError) as exc:
                raise SensorValidationError(
                    f"Sensor reading is structurally invalid: field {key!r} "
                    f"value {raw!r} is not castable to float. This indicates "
                    "a programming error in the upstream producer."
                ) from exc
        return values


    def _update_stuck_run(self, key: str, value: float) -> bool:
        reference = self._stuck_reference[key]
        epsilon = self._config.STUCK_EPSILON[key]
        if reference is not None and abs(value - reference) <= epsilon:
            self._stuck_run_length[key] += 1
        else:
            self._stuck_reference[key] = value
            self._stuck_run_length[key] = 1
        return self._stuck_run_length[key] >= self._config.STUCK_TICK_LIMIT


    def _advance_state(
        self,
        reading: SensorReading,
        values: Dict[str, float],
        out_of_range: Dict[str, bool],
        spiked: Dict[str, bool],
    ) -> None:
        for key in self._config.SENSOR_KEYS:
            if not out_of_range[key] and not spiked[key]:
                self._spike_baseline[key] = values[key]
        if self._last_timestamp is None or reading.timestamp > self._last_timestamp:
            self._last_timestamp = reading.timestamp


    def _normalize(self, key: str, value: float) -> float:
        p_lo, p_hi = self._config.SENSORS[key]["plausible_range"]
        return _clamp((value - p_lo) / (p_hi - p_lo), 0.0, 1.0)

    def _deviation(self, key: str, value: float) -> float:
        spec = self._config.SENSORS[key]
        n_lo, n_hi = spec["nominal_band"]
        if value > n_hi:
            c_hi = spec["critical_high"]
            if c_hi is None:
                return 0.0
            return _clamp((value - n_hi) / (c_hi - n_hi), 0.0, 1.0)
        if value < n_lo:
            c_lo = spec["critical_low"]
            if c_lo is None:
                return 0.0
            return _clamp((n_lo - value) / (n_lo - c_lo), 0.0, 1.0)
        return 0.0


    def _log_flags(
        self,
        reading: SensorReading,
        values: Dict[str, float],
        flags: List[SensorFlag],
    ) -> None:
        for flag in flags:
            if flag.sensor_key is None:
                self._logger.warning(
                    "Validation flag %s at tick %d (timestamp %s).",
                    flag.flag.name,
                    reading.tick,
                    reading.timestamp.isoformat(),
                )
            else:
                self._logger.warning(
                    "Validation flag %s on sensor %s (value %.4f) at tick %d.",
                    flag.flag.name,
                    flag.sensor_key,
                    values[flag.sensor_key],
                    reading.tick,
                )


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
