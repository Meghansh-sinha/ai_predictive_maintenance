
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from ai.prompt_builder import (
    MAX_PROBABLE_CAUSES,
    MAX_RECOMMENDED_ACTIONS,
    build_analysis_prompt,
)
from models.data_models import (
    HealthResult,
    HistorySummary,
    MachineStatus,
    MaintenancePriority,
    ProductionImpact,
    TrendDirection,
)

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_MAX_PROMPT_CHARS = 4000


def make_result() -> HealthResult:
    return HealthResult(
        machine_id=config.MACHINE_ID,
        timestamp=_T0,
        health_score=72.5,
        machine_status=MachineStatus.WARNING,
        confidence_score=88.0,
        trend=TrendDirection.DEGRADING,
        trend_slope=-0.32,
        maintenance_priority=MaintenancePriority.HIGH,
        downtime_risk_pct=41.2,
        production_impact=ProductionImpact(49.44, 53395.2, "High"),
        sensor_health={
            "temperature_c": 70.0,
            "vibration_mm_s": 60.0,
            "pressure_bar": 95.0,
            "current_a": 100.0,
        },
        sensor_contributions={
            "temperature_c": 9.0,
            "vibration_mm_s": 14.0,
            "pressure_bar": 1.0,
            "current_a": 0.0,
            "trend_penalty": 3.2,
        },
        alerts=("SPIKE_DETECTED on Vibration.",),
        used_fallback_values=False,
    )


def make_summary() -> HistorySummary:
    return HistorySummary(
        window_length=120,
        start_time=_T0 - timedelta(minutes=4),
        end_time=_T0,
        health_min=70.1,
        health_mean=85.3,
        health_max=99.8,
        health_delta=-25.4,
        sensor_stats={
            key: {"min": 1.0, "mean": 2.0, "max": 3.0}
            for key in config.SENSOR_KEYS
        },
        invalid_count=4,
        critical_count=0,
    )


def test_prompt_is_deterministic_for_fixed_input() -> None:
    first = build_analysis_prompt(make_result(), make_summary(), config)
    second = build_analysis_prompt(make_result(), make_summary(), config)
    assert first == second


def test_prompt_contains_required_instructions_and_context() -> None:
    prompt = build_analysis_prompt(make_result(), make_summary(), config)
    assert "senior reliability engineer" in prompt
    assert "Do not invent sensor values." in prompt
    assert config.MACHINE_NAME in prompt
    assert config.MACHINE_ID in prompt
    for key in config.SENSOR_KEYS:
        assert config.SENSORS[key]["display_name"] in prompt
        assert config.SENSORS[key]["unit"] in prompt
    for required in (
        '"summary"',
        '"probable_causes"',
        '"recommended_actions"',
        '"urgency_note"',
    ):
        assert required in prompt
    assert str(MAX_PROBABLE_CAUSES) in prompt
    assert str(MAX_RECOMMENDED_ACTIONS) in prompt
    assert "single JSON object" in prompt
    assert "no markdown fences" in prompt
    assert "220 words" in prompt
    assert "dominant contributing sensor" in prompt


def test_prompt_contains_processed_metrics() -> None:
    prompt = build_analysis_prompt(make_result(), make_summary(), config)
    assert '"health_score": 72.5' in prompt
    assert '"machine_status": "WARNING"' in prompt
    assert '"maintenance_priority": "HIGH"' in prompt
    assert '"trend": "DEGRADING"' in prompt
    assert '"downtime_risk_pct": 41.2' in prompt


def test_prompt_excludes_tick_by_tick_data() -> None:
    prompt = build_analysis_prompt(make_result(), make_summary(), config)
    assert "window_length_ticks" in prompt
    assert '"tick"' not in prompt
    assert "timestamp_series" not in prompt
    assert prompt.count("2026-01-01T") == 2


def test_prompt_length_bound_for_canonical_fixture() -> None:
    prompt = build_analysis_prompt(make_result(), make_summary(), config)
    assert len(prompt) <= _MAX_PROMPT_CHARS
