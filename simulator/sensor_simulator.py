
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Dict, Optional

from models.data_models import SensorReading, SimulationScenario
from utils.logger import get_logger

_DEBUG_LOG_SAMPLE_EVERY = 10


class SensorSimulator:

    def __init__(self, config: ModuleType, seed: Optional[int] = None) -> None:
        self._config = config
        self._rng = random.Random(seed)
        self._logger = get_logger(__name__)
        self._scenario = SimulationScenario.NORMAL
        self._tick = 0
        self._drift_state: Dict[str, float] = {
            key: 0.0 for key in config.SENSOR_KEYS
        }
        self._last_timestamp: Optional[datetime] = None


    def set_scenario(self, scenario: SimulationScenario) -> None:
        if scenario is not self._scenario:
            self._logger.info(
                "Scenario changed: %s -> %s (drift preserved).",
                self._scenario.name,
                scenario.name,
            )
        self._scenario = scenario

    def generate_reading(self) -> SensorReading:
        tick = self._tick
        self._advance_drift()

        values: Dict[str, float] = {}
        for key in self._config.SENSOR_KEYS:
            values[key] = self._generate_sensor_value(key, tick)

        timestamp = self._next_timestamp()
        reading = SensorReading(
            machine_id=self._config.MACHINE_ID,
            timestamp=timestamp,
            temperature_c=values["temperature_c"],
            vibration_mm_s=values["vibration_mm_s"],
            pressure_bar=values["pressure_bar"],
            current_a=values["current_a"],
            tick=tick,
        )

        if tick % _DEBUG_LOG_SAMPLE_EVERY == 0:
            self._logger.debug(
                "tick=%d scenario=%s values=%s",
                tick,
                self._scenario.name,
                {key: round(value, 3) for key, value in values.items()},
            )

        self._tick += 1
        return reading

    def reset(self) -> None:
        self._tick = 0
        self._drift_state = {key: 0.0 for key in self._config.SENSOR_KEYS}
        self._last_timestamp = None
        self._logger.info("Simulator reset: drift state and tick counter cleared.")


    def _advance_drift(self) -> None:
        scenario_name = self._scenario.name
        vibration_rate = self._config.SENSORS["vibration_mm_s"]["drift_per_tick"][
            scenario_name
        ]

        for key in self._config.SENSOR_KEYS:
            spec = self._config.SENSORS[key]
            rate = spec["drift_per_tick"][scenario_name]
            if key == "temperature_c":
                rate += self._config.VIBRATION_TO_TEMPERATURE_COUPLING * vibration_rate
            new_drift = self._drift_state[key] + rate

            p_lo, p_hi = spec["plausible_range"]
            span = p_hi - p_lo
            half_margin = (self._config.DRIFT_CLAMP_FACTOR - 1.0) * span / 2.0
            allowed_lo = p_lo - half_margin
            allowed_hi = p_hi + half_margin
            baseline = spec["baseline"]
            drifted_center = baseline + new_drift
            drifted_center = min(max(drifted_center, allowed_lo), allowed_hi)
            self._drift_state[key] = drifted_center - baseline

    def _generate_sensor_value(self, key: str, tick: int) -> float:
        spec = self._config.SENSORS[key]
        value = spec["baseline"] + self._drift_state[key]
        value += spec["cycle_amplitude"] * math.sin(
            2.0 * math.pi * tick / spec["cycle_period_ticks"]
        )
        value += self._rng.gauss(0.0, spec["noise_sigma"])

        spike_probability = self._config.SPIKE_PROBABILITY[self._scenario.name]
        if self._rng.random() < spike_probability:
            value += spec["spike_direction"] * spec["spike_magnitude"]

        return value

    def _next_timestamp(self) -> datetime:
        now = datetime.now(timezone.utc)
        if self._last_timestamp is not None and now <= self._last_timestamp:
            now = self._last_timestamp + timedelta(microseconds=1)
        self._last_timestamp = now
        return now
