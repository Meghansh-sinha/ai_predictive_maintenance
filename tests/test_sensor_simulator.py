
from __future__ import annotations

import math
from typing import List

import config
from models.data_models import SensorReading, SimulationScenario
from simulator import SensorSimulator

_SEED = 42


def run_ticks(
    simulator: SensorSimulator, n: int
) -> List[SensorReading]:
    return [simulator.generate_reading() for _ in range(n)]


def values(readings: List[SensorReading], key: str) -> List[float]:
    return [getattr(reading, key) for reading in readings]


def mean(sequence: List[float]) -> float:
    return sum(sequence) / len(sequence)


def expected_deterministic_part(key: str, tick: int, drift: float = 0.0) -> float:
    spec = config.SENSORS[key]
    return (
        spec["baseline"]
        + drift
        + spec["cycle_amplitude"]
        * math.sin(2.0 * math.pi * tick / spec["cycle_period_ticks"])
    )




def test_same_seed_produces_identical_value_sequence() -> None:
    sim_a = SensorSimulator(config, seed=_SEED)
    sim_b = SensorSimulator(config, seed=_SEED)
    readings_a = run_ticks(sim_a, 100)
    readings_b = run_ticks(sim_b, 100)
    for key in config.SENSOR_KEYS:
        assert values(readings_a, key) == values(readings_b, key)
    assert [r.tick for r in readings_a] == [r.tick for r in readings_b]


def test_different_seeds_produce_different_sequences() -> None:
    sim_a = SensorSimulator(config, seed=1)
    sim_b = SensorSimulator(config, seed=2)
    readings_a = run_ticks(sim_a, 50)
    readings_b = run_ticks(sim_b, 50)
    assert values(readings_a, "vibration_mm_s") != values(readings_b, "vibration_mm_s")




def test_reading_identity_tick_sequence_and_monotonic_timestamps() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    readings = run_ticks(simulator, 25)
    assert all(r.machine_id == config.MACHINE_ID for r in readings)
    assert [r.tick for r in readings] == list(range(25))
    timestamps = [r.timestamp for r in readings]
    assert all(later > earlier for earlier, later in zip(timestamps, timestamps[1:]))
    assert all(r.timestamp.tzinfo is not None for r in readings)




def test_normal_scenario_stays_within_plausible_ranges_over_500_ticks() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    readings = run_ticks(simulator, 500)
    for key in config.SENSOR_KEYS:
        p_lo, p_hi = config.SENSORS[key]["plausible_range"]
        for value in values(readings, key):
            assert p_lo <= value <= p_hi, (key, value)




def _tail_mean_for_scenario(scenario: SimulationScenario, key: str) -> float:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(scenario)
    readings = run_ticks(simulator, 200)
    return mean(values(readings[-20:], key))


def test_gradual_vs_rapid_drift_ordering_on_vibration_and_temperature() -> None:
    for key in ("vibration_mm_s", "temperature_c"):
        normal = _tail_mean_for_scenario(SimulationScenario.NORMAL, key)
        gradual = _tail_mean_for_scenario(SimulationScenario.GRADUAL_DEGRADATION, key)
        rapid = _tail_mean_for_scenario(SimulationScenario.RAPID_DEGRADATION, key)
        assert rapid > gradual > normal, (key, normal, gradual, rapid)


def test_pressure_drifts_downward_under_degradation() -> None:
    normal = _tail_mean_for_scenario(SimulationScenario.NORMAL, "pressure_bar")
    rapid = _tail_mean_for_scenario(
        SimulationScenario.RAPID_DEGRADATION, "pressure_bar"
    )
    assert rapid < normal


def test_temperature_drift_includes_vibration_coupling() -> None:
    scenario = SimulationScenario.GRADUAL_DEGRADATION.name
    own_rate = config.SENSORS["temperature_c"]["drift_per_tick"][scenario]
    vibration_rate = config.SENSORS["vibration_mm_s"]["drift_per_tick"][scenario]
    expected_rate = (
        own_rate + config.VIBRATION_TO_TEMPERATURE_COUPLING * vibration_rate
    )

    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.GRADUAL_DEGRADATION)
    n = 400
    readings = run_ticks(simulator, n)
    tail = readings[-40:]
    observed = mean(
        [
            r.temperature_c - expected_deterministic_part("temperature_c", r.tick)
            for r in tail
        ]
    )
    expected_drift_at_tail = expected_rate * (n - 20)
    assert abs(observed - expected_drift_at_tail) < 1.5




def test_rapid_drift_is_clamped_near_expanded_plausible_range() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.RAPID_DEGRADATION)
    readings = run_ticks(simulator, 2000)
    spec = config.SENSORS["temperature_c"]
    p_lo, p_hi = spec["plausible_range"]
    span = p_hi - p_lo
    half_margin = (config.DRIFT_CLAMP_FACTOR - 1.0) * span / 2.0
    ceiling = (
        p_hi
        + half_margin
        + spec["cycle_amplitude"]
        + spec["spike_magnitude"]
        + 5.0 * spec["noise_sigma"]
    )
    assert max(values(readings, "temperature_c")) <= ceiling




def _count_spike_like_events(
    readings: List[SensorReading], key: str, drift_free: bool
) -> int:
    assert drift_free
    spec = config.SENSORS[key]
    threshold = 0.6 * spec["spike_magnitude"]
    count = 0
    for reading in readings:
        expected = expected_deterministic_part(key, reading.tick)
        if abs(getattr(reading, key) - expected) > threshold:
            count += 1
    return count


def test_intermittent_fault_spike_frequency_within_statistical_bounds() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.INTERMITTENT_FAULT)
    readings = run_ticks(simulator, 500)
    count = _count_spike_like_events(readings, "vibration_mm_s", drift_free=True)
    expected = config.SPIKE_PROBABILITY["INTERMITTENT_FAULT"] * 500
    assert 0.5 * expected <= count <= 1.6 * expected, count


def test_normal_spike_frequency_is_rare() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    readings = run_ticks(simulator, 500)
    count = _count_spike_like_events(readings, "vibration_mm_s", drift_free=True)
    assert count <= 20


def test_pressure_spikes_are_biased_toward_pressure_loss() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.INTERMITTENT_FAULT)
    readings = run_ticks(simulator, 500)
    spec = config.SENSORS["pressure_bar"]
    threshold = 0.6 * spec["spike_magnitude"]
    deltas = [
        reading.pressure_bar
        - expected_deterministic_part("pressure_bar", reading.tick)
        for reading in readings
    ]
    spikes = [d for d in deltas if abs(d) > threshold]
    assert spikes, "expected spike events under INTERMITTENT_FAULT"
    assert all(d < 0 for d in spikes)




def test_scenario_switch_preserves_drift() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.RAPID_DEGRADATION)
    run_ticks(simulator, 100)
    simulator.set_scenario(SimulationScenario.NORMAL)
    after_switch = run_ticks(simulator, 20)
    elevated = mean(values(after_switch, "vibration_mm_s"))
    baseline = config.SENSORS["vibration_mm_s"]["baseline"]
    accumulated = (
        config.SENSORS["vibration_mm_s"]["drift_per_tick"]["RAPID_DEGRADATION"] * 100
    )
    assert elevated > baseline + 0.5 * accumulated


def test_reset_clears_drift_and_tick_counter() -> None:
    simulator = SensorSimulator(config, seed=_SEED)
    simulator.set_scenario(SimulationScenario.RAPID_DEGRADATION)
    run_ticks(simulator, 150)
    simulator.reset()

    first = simulator.generate_reading()
    assert first.tick == 0

    simulator.set_scenario(SimulationScenario.NORMAL)
    readings = run_ticks(simulator, 20)
    spec = config.SENSORS["vibration_mm_s"]
    near_baseline = mean(values(readings, "vibration_mm_s"))
    assert abs(near_baseline - spec["baseline"]) < (
        spec["cycle_amplitude"] + 4.0 * spec["noise_sigma"] + spec["spike_magnitude"]
    )
    residuals = [
        r.vibration_mm_s - expected_deterministic_part("vibration_mm_s", r.tick)
        for r in readings
        if abs(
            r.vibration_mm_s
            - expected_deterministic_part("vibration_mm_s", r.tick)
        )
        < 0.6 * spec["spike_magnitude"]
    ]
    assert abs(mean(residuals)) < 4.0 * spec["noise_sigma"]


def test_generate_reading_never_raises_over_long_runs() -> None:
    for scenario in SimulationScenario:
        simulator = SensorSimulator(config, seed=_SEED)
        simulator.set_scenario(scenario)
        readings = run_ticks(simulator, 300)
        assert len(readings) == 300
