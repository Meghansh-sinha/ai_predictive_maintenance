
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from utils.exceptions import ConfigurationError


MACHINE_ID: str = "MACHINE-01"
MACHINE_NAME: str = "Primary Coolant Pump P-101"

SENSOR_KEYS: Tuple[str, ...] = (
    "temperature_c",
    "vibration_mm_s",
    "pressure_bar",
    "current_a",
)

SCENARIO_NAMES: Tuple[str, ...] = (
    "NORMAL",
    "GRADUAL_DEGRADATION",
    "RAPID_DEGRADATION",
    "INTERMITTENT_FAULT",
)

SENSORS: Mapping[str, Mapping[str, Any]] = {
    "temperature_c": {
        "display_name": "Temperature",
        "unit": "°C",
        "plausible_range": (10.0, 120.0),
        "nominal_band": (55.0, 75.0),
        "warning_bands": ((75.0, 90.0),),
        "critical_low": 20.0,
        "critical_high": 90.0,
        "baseline": 65.0,
        "noise_sigma": 0.8,
        "cycle_amplitude": 1.5,
        "cycle_period_ticks": 60,
        "drift_per_tick": {
            "NORMAL": 0.0,
            "GRADUAL_DEGRADATION": 0.03,
            "RAPID_DEGRADATION": 0.18,
            "INTERMITTENT_FAULT": 0.0,
        },
        "spike_magnitude": 6.0,
        "spike_direction": +1.0,
    },
    "vibration_mm_s": {
        "display_name": "Vibration",
        "unit": "mm/s RMS",
        "plausible_range": (0.0, 8.0),
        "nominal_band": (1.0, 2.8),
        "warning_bands": ((2.8, 4.5),),
        "critical_low": None,
        "critical_high": 4.5,
        "baseline": 1.8,
        "noise_sigma": 0.12,
        "cycle_amplitude": 0.15,
        "cycle_period_ticks": 45,
        "drift_per_tick": {
            "NORMAL": 0.0,
            "GRADUAL_DEGRADATION": 0.004,
            "RAPID_DEGRADATION": 0.024,
            "INTERMITTENT_FAULT": 0.0,
        },
        "spike_magnitude": 1.5,
        "spike_direction": +1.0,
    },
    "pressure_bar": {
        "display_name": "Pressure",
        "unit": "bar",
        "plausible_range": (0.0, 10.0),
        "nominal_band": (4.0, 6.0),
        "warning_bands": ((3.2, 4.0), (6.0, 7.0)),
        "critical_low": 3.2,
        "critical_high": 7.0,
        "baseline": 5.0,
        "noise_sigma": 0.12,
        "cycle_amplitude": 0.2,
        "cycle_period_ticks": 50,
        "drift_per_tick": {
            "NORMAL": 0.0,
            "GRADUAL_DEGRADATION": -0.002,
            "RAPID_DEGRADATION": -0.012,
            "INTERMITTENT_FAULT": 0.0,
        },
        "spike_magnitude": 0.9,
        "spike_direction": -1.0,
    },
    "current_a": {
        "display_name": "Motor Current",
        "unit": "A",
        "plausible_range": (0.0, 40.0),
        "nominal_band": (16.0, 24.0),
        "warning_bands": ((24.0, 30.0),),
        "critical_low": 10.0,
        "critical_high": 30.0,
        "baseline": 20.0,
        "noise_sigma": 0.5,
        "cycle_amplitude": 0.8,
        "cycle_period_ticks": 40,
        "drift_per_tick": {
            "NORMAL": 0.0,
            "GRADUAL_DEGRADATION": 0.01,
            "RAPID_DEGRADATION": 0.06,
            "INTERMITTENT_FAULT": 0.0,
        },
        "spike_magnitude": 4.0,
        "spike_direction": +1.0,
    },
}

SPIKE_PROBABILITY: Mapping[str, float] = {
    "NORMAL": 0.01,
    "GRADUAL_DEGRADATION": 0.01,
    "RAPID_DEGRADATION": 0.01,
    "INTERMITTENT_FAULT": 0.12,
}

VIBRATION_TO_TEMPERATURE_COUPLING: float = 0.30

DRIFT_CLAMP_FACTOR: float = 1.05


TICK_INTERVAL_S: float = 2.0
HISTORY_MAX_LEN: int = 500
TREND_WINDOW: int = 30
CONFIDENCE_WINDOW: int = 50


SPIKE_DELTA_LIMIT: Mapping[str, float] = {
    "temperature_c": 4.0,
    "vibration_mm_s": 0.9,
    "pressure_bar": 0.7,
    "current_a": 3.0,
}
STUCK_EPSILON: Mapping[str, float] = {
    "temperature_c": 0.01,
    "vibration_mm_s": 0.001,
    "pressure_bar": 0.001,
    "current_a": 0.01,
}
STUCK_TICK_LIMIT: int = 15
CV_REF: float = 0.35
TREND_MIN_POINTS: int = 5


SENSOR_WEIGHTS: Mapping[str, float] = {
    "vibration_mm_s": 0.35,
    "temperature_c": 0.30,
    "pressure_bar": 0.20,
    "current_a": 0.15,
}

STATUS_THRESHOLDS: Mapping[str, float] = {"HEALTHY": 80.0, "WARNING": 55.0}
STATUS_HYSTERESIS: float = 3.0

TREND_DEGRADING_SLOPE: float = -0.15
TREND_IMPROVING_SLOPE: float = +0.15

TREND_PENALTY_MULTIPLIER: float = 10.0
TREND_PENALTY_CAP: float = 5.0

CONFIDENCE_WEIGHTS: Mapping[str, float] = {
    "data_validity": 0.40,
    "window_fill": 0.20,
    "signal_stability": 0.25,
    "range_compliance": 0.15,
}
STABILITY_MEAN_EXCLUSION: float = 0.05
FALLBACK_CONFIDENCE_CAP: float = 60.0


NOMINAL_THROUGHPUT_UNITS_HR: float = 120.0
UNIT_VALUE: float = 45.0
CURRENCY_SYMBOL: str = "$"
IMPACT_HORIZON_HR: float = 24.0

DOWNTIME_RISK_MIDPOINT: float = 45.0
DOWNTIME_RISK_STEEPNESS: float = 9.0
DOWNTIME_TREND_FACTOR: float = 25.0
DOWNTIME_RISK_MIN: float = 1.0
DOWNTIME_RISK_MAX: float = 99.0

PRIORITY_MATRIX: Mapping[str, Mapping[str, str]] = {
    "HEALTHY": {"IMPROVING": "LOW", "STABLE": "LOW", "DEGRADING": "MEDIUM"},
    "WARNING": {"IMPROVING": "MEDIUM", "STABLE": "MEDIUM", "DEGRADING": "HIGH"},
    "CRITICAL": {"IMPROVING": "HIGH", "STABLE": "URGENT", "DEGRADING": "URGENT"},
}
PRIORITY_RISK_OVERRIDES: Mapping[str, float] = {"URGENT": 85.0, "HIGH": 65.0}

IMPACT_LEVEL_BANDS: Tuple[Tuple[str, Optional[float]], ...] = (
    ("Low", 5_000.0),
    ("Moderate", 25_000.0),
    ("High", 75_000.0),
    ("Severe", None),
)


GEMINI_MODEL_DEFAULT: str = "gemini-2.0-flash"
AI_REQUEST_TIMEOUT_S: float = 20.0
AI_MAX_RETRIES: int = 1
AI_RETRY_BACKOFF_S: float = 2.0
AI_MAX_OUTPUT_TOKENS: int = 1024
AI_TEMPERATURE: float = 0.4
AI_STALENESS_SCORE_DELTA: float = 5.0
AI_FALLBACK_MODEL_NAME: str = "rule-based-fallback"


REPORTS_DIR: str = "reports"
PDF_FILENAME_PATTERN: str = "maintenance_report_{machine_id}_{timestamp}.pdf"
PDF_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"
PDF_PAGE_SIZE: str = "A4"
PDF_MARGIN_MM: float = 18.0
PDF_REPORT_TITLE: str = "Predictive Maintenance Report"
PDF_HEADING_COLOR: str = "#263238"
PDF_FOOTER_TEXT: str = (
    "Generated by AI Predictive Maintenance Dashboard — estimates are model-based."
)
PDF_TREND_MAX_POINTS: int = 120
PDF_ALERTS_APPENDIX_MAX: int = 20


PAGE_TITLE: str = "AI Predictive Maintenance Dashboard"
PAGE_ICON: str = "🛠"
PAGE_LAYOUT: str = "wide"

STATUS_COLORS: Mapping[str, str] = {
    "HEALTHY": "#2E7D32",
    "WARNING": "#F9A825",
    "CRITICAL": "#C62828",
}
PLOTLY_TEMPLATE: str = "plotly_white"
STATUS_BAND_OPACITY: float = 0.10

REFRESH_INTERVAL_MIN_S: float = 1.0
REFRESH_INTERVAL_MAX_S: float = 10.0

ALERTS_PANEL_MAX: int = 15
DATA_TABLE_ROWS: int = 25


LOG_DIR: str = "logs"
LOG_FILE: str = "app.log"
LOG_LEVEL_FILE: str = "DEBUG"
LOG_LEVEL_CONSOLE: str = "WARNING"
LOG_MAX_BYTES: int = 1_000_000
LOG_BACKUP_COUNT: int = 3


_WEIGHT_SUM_TOLERANCE: float = 1e-9


def validate_config() -> None:
    problems: list[str] = []

    if set(SENSOR_WEIGHTS) != set(SENSOR_KEYS):
        problems.append(
            "SENSOR_WEIGHTS keys must exactly match SENSOR_KEYS; "
            f"got {sorted(SENSOR_WEIGHTS)} vs {sorted(SENSOR_KEYS)}."
        )
    weight_sum = sum(SENSOR_WEIGHTS.values())
    if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
        problems.append(f"SENSOR_WEIGHTS must sum to 1.0; got {weight_sum!r}.")

    conf_sum = sum(CONFIDENCE_WEIGHTS.values())
    if abs(conf_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
        problems.append(f"CONFIDENCE_WEIGHTS must sum to 1.0; got {conf_sum!r}.")

    if set(SENSORS) != set(SENSOR_KEYS):
        problems.append(
            "SENSORS keys must exactly match SENSOR_KEYS; "
            f"got {sorted(SENSORS)} vs {sorted(SENSOR_KEYS)}."
        )

    for key in SENSOR_KEYS:
        spec: Mapping[str, Any] = SENSORS.get(key, {})
        p_lo, p_hi = spec.get("plausible_range", (0.0, 0.0))
        n_lo, n_hi = spec.get("nominal_band", (0.0, 0.0))
        c_lo = spec.get("critical_low")
        c_hi = spec.get("critical_high")
        if not p_lo < p_hi:
            problems.append(f"{key}: plausible_range must satisfy lo < hi.")
        if not (p_lo <= n_lo < n_hi <= p_hi):
            problems.append(
                f"{key}: nominal_band {n_lo, n_hi} must lie within "
                f"plausible_range {p_lo, p_hi}."
            )
        if c_hi is not None and not (n_hi < c_hi <= p_hi):
            problems.append(
                f"{key}: critical_high {c_hi} must satisfy "
                f"nominal high {n_hi} < critical_high <= plausible high {p_hi}."
            )
        if c_lo is not None and not (p_lo <= c_lo < n_lo):
            problems.append(
                f"{key}: critical_low {c_lo} must satisfy "
                f"plausible low {p_lo} <= critical_low < nominal low {n_lo}."
            )
        drift: Mapping[str, float] = spec.get("drift_per_tick", {})
        if set(drift) != set(SCENARIO_NAMES):
            problems.append(f"{key}: drift_per_tick must cover all SCENARIO_NAMES.")
        if key not in SPIKE_DELTA_LIMIT:
            problems.append(f"SPIKE_DELTA_LIMIT missing sensor {key!r}.")
        if key not in STUCK_EPSILON:
            problems.append(f"STUCK_EPSILON missing sensor {key!r}.")

    if set(SPIKE_PROBABILITY) != set(SCENARIO_NAMES):
        problems.append("SPIKE_PROBABILITY must cover all SCENARIO_NAMES.")

    if not (
        0.0 < STATUS_THRESHOLDS["WARNING"] < STATUS_THRESHOLDS["HEALTHY"] < 100.0
    ):
        problems.append(
            "STATUS_THRESHOLDS must satisfy 0 < WARNING < HEALTHY < 100; "
            f"got {dict(STATUS_THRESHOLDS)}."
        )

    if not TREND_DEGRADING_SLOPE < 0.0 < TREND_IMPROVING_SLOPE:
        problems.append(
            "Trend slopes must satisfy TREND_DEGRADING_SLOPE < 0 < "
            "TREND_IMPROVING_SLOPE."
        )

    if not DOWNTIME_RISK_MIN < DOWNTIME_RISK_MAX:
        problems.append("DOWNTIME_RISK_MIN must be below DOWNTIME_RISK_MAX.")

    if set(PRIORITY_MATRIX) != {"HEALTHY", "WARNING", "CRITICAL"}:
        problems.append("PRIORITY_MATRIX must have exactly the three status rows.")
    for status, row in PRIORITY_MATRIX.items():
        if set(row) != {"IMPROVING", "STABLE", "DEGRADING"}:
            problems.append(f"PRIORITY_MATRIX[{status!r}] must cover all trends.")

    if IMPACT_LEVEL_BANDS[-1][1] is not None:
        problems.append("IMPACT_LEVEL_BANDS must end with an open-ended top band.")

    if not (
        0.0 < REFRESH_INTERVAL_MIN_S <= TICK_INTERVAL_S <= REFRESH_INTERVAL_MAX_S
    ):
        problems.append(
            "TICK_INTERVAL_S must lie within the sidebar refresh bounds "
            f"[{REFRESH_INTERVAL_MIN_S}, {REFRESH_INTERVAL_MAX_S}]."
        )

    if not 0 < TREND_MIN_POINTS <= TREND_WINDOW <= HISTORY_MAX_LEN:
        problems.append(
            "Windows must satisfy 0 < TREND_MIN_POINTS <= TREND_WINDOW "
            "<= HISTORY_MAX_LEN."
        )
    if not 0 < CONFIDENCE_WINDOW <= HISTORY_MAX_LEN:
        problems.append("CONFIDENCE_WINDOW must be within (0, HISTORY_MAX_LEN].")

    if problems:
        raise ConfigurationError(
            "Configuration is invalid — fix config.py before running. "
            + " ".join(problems)
        )
