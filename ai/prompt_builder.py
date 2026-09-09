
from __future__ import annotations

import json
from types import ModuleType
from typing import Any, Dict

from models.data_models import HealthResult, HistorySummary

MAX_PROBABLE_CAUSES = 4
MAX_RECOMMENDED_ACTIONS = 5
_MAX_WORDS = 220

_ROLE_FRAME = (
    "You are a senior reliability engineer writing a concise assessment "
    "for a plant operations manager. Base your analysis ONLY on the data "
    "provided. Do not invent sensor values."
)

_FLOAT_PRECISION = 3


def _rounded(value: float) -> float:
    return round(float(value), _FLOAT_PRECISION)


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def build_analysis_prompt(
    result: HealthResult, history_summary: HistorySummary, config: ModuleType
) -> str:
    machine_context = "\n".join(
        [
            f"Machine: {config.MACHINE_NAME} (ID: {config.MACHINE_ID})",
            "Sensors (unit, nominal band):",
        ]
        + [
            (
                f"- {config.SENSORS[key]['display_name']} "
                f"({config.SENSORS[key]['unit']}), nominal "
                f"{config.SENSORS[key]['nominal_band'][0]}-"
                f"{config.SENSORS[key]['nominal_band'][1]}"
            )
            for key in config.SENSOR_KEYS
        ]
    )

    assessment: Dict[str, Any] = {
        "health_score": _rounded(result.health_score),
        "machine_status": result.machine_status.name,
        "confidence_score": _rounded(result.confidence_score),
        "trend": result.trend.value,
        "trend_slope_points_per_tick": _rounded(result.trend_slope),
        "maintenance_priority": result.maintenance_priority.name,
        "downtime_risk_pct": _rounded(result.downtime_risk_pct),
        "production_impact": {
            "throughput_at_risk_units_hr": _rounded(
                result.production_impact.throughput_at_risk_units_hr
            ),
            "estimated_loss_per_day": _rounded(
                result.production_impact.estimated_loss_per_day
            ),
            "impact_level": result.production_impact.impact_level,
        },
        "sensor_raw_value_stats": {
            key: {
                stat: _rounded(value)
                for stat, value in history_summary.sensor_stats[key].items()
            }
            for key in config.SENSOR_KEYS
        },
        "sensor_health": {
            key: _rounded(result.sensor_health[key])
            for key in config.SENSOR_KEYS
        },
        "sensor_contributions": {
            key: _rounded(value)
            for key, value in sorted(result.sensor_contributions.items())
        },
        "active_alerts": list(result.alerts),
        "used_fallback_values": result.used_fallback_values,
    }

    history_block: Dict[str, Any] = {
        "window_length_ticks": history_summary.window_length,
        "window_start_utc": history_summary.start_time.isoformat(),
        "window_end_utc": history_summary.end_time.isoformat(),
        "health_score_min": _rounded(history_summary.health_min),
        "health_score_mean": _rounded(history_summary.health_mean),
        "health_score_max": _rounded(history_summary.health_max),
        "health_delta_current_vs_window_start": _rounded(
            history_summary.health_delta
        ),
        "invalid_reading_count": history_summary.invalid_count,
        "critical_tick_count": history_summary.critical_count,
    }

    task = "\n".join(
        [
            "Task: respond with a single JSON object, no markdown fences, "
            "keys exactly:",
            '- "summary": string, 2-4 sentences',
            (
                f'- "probable_causes": array of at most {MAX_PROBABLE_CAUSES} '
                "short strings, most likely first"
            ),
            (
                f'- "recommended_actions": array of at most '
                f"{MAX_RECOMMENDED_ACTIONS} short strings, imperative voice, "
                "most urgent first"
            ),
            '- "urgency_note": string, one sentence tying urgency to the '
            "maintenance priority and downtime risk",
            "Reference the dominant contributing sensor(s) by name. Keep the "
            f"total under {_MAX_WORDS} words. Do not recommend actions "
            "outside operator/maintenance scope.",
        ]
    )

    return "\n\n".join(
        [
            _ROLE_FRAME,
            machine_context,
            "Current assessment:\n" + _dumps(assessment),
            "Recent history (aggregates only):\n" + _dumps(history_block),
            task,
        ]
    )
