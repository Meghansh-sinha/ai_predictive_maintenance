
from __future__ import annotations

import statistics
from types import ModuleType
from typing import Dict, List, Optional, Tuple

import numpy as np

from health_engine.business_metrics import (
    compute_downtime_risk,
    compute_maintenance_priority,
    compute_production_impact,
)
from models.data_models import (
    HealthResult,
    MachineStatus,
    MaintenancePriority,
    TrendDirection,
    ValidatedReading,
)
from utils.exceptions import AnalysisError, ConfigurationError
from utils.history import HistoryBuffer
from utils.logger import get_logger

TREND_PENALTY_KEY = "trend_penalty"

_WEIGHT_SUM_TOLERANCE = 1e-9


class HealthAnalysisEngine:

    def __init__(self, config: ModuleType) -> None:
        self._config = config
        self._logger = get_logger(__name__)
        if set(config.SENSOR_WEIGHTS) != set(config.SENSOR_KEYS):
            raise ConfigurationError(
                "SENSOR_WEIGHTS keys must exactly match SENSOR_KEYS; got "
                f"{sorted(config.SENSOR_WEIGHTS)} vs {sorted(config.SENSOR_KEYS)}."
            )
        weight_sum = sum(config.SENSOR_WEIGHTS.values())
        if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ConfigurationError(
                f"SENSOR_WEIGHTS must sum to 1.0; got {weight_sum!r}."
            )


    def analyze(
        self, validated: ValidatedReading, history: HistoryBuffer
    ) -> HealthResult:
        self._check_precondition(validated)

        deviations, used_fallback, fallback_alerts = (
            self._resolve_effective_deviations(validated, history)
        )
        sensor_health = {
            key: 100.0 * (1.0 - deviations[key])
            for key in self._config.SENSOR_KEYS
        }
        base_score = sum(
            self._config.SENSOR_WEIGHTS[key] * sensor_health[key]
            for key in self._config.SENSOR_KEYS
        )

        trend, trend_slope = self._compute_trend(history)
        penalty = self._trend_penalty(trend, trend_slope, base_score)
        score_unrounded = min(max(base_score - penalty, 0.0), 100.0)
        health_score = round(score_unrounded, 1)

        contributions: Dict[str, float] = {
            key: self._config.SENSOR_WEIGHTS[key] * (100.0 - sensor_health[key])
            for key in self._config.SENSOR_KEYS
        }
        if penalty > 0.0:
            contributions[TREND_PENALTY_KEY] = penalty

        previous = history.latest()
        previous_status = previous[1].machine_status if previous else None
        previous_priority = previous[1].maintenance_priority if previous else None

        status = self._status_with_hysteresis(health_score, previous_status)
        confidence = self._compute_confidence(validated, history, used_fallback)
        downtime_risk = compute_downtime_risk(
            health_score, trend_slope, self._config
        )
        priority = compute_maintenance_priority(
            status, trend, downtime_risk, self._config
        )
        impact = compute_production_impact(downtime_risk, self._config)

        alerts = self._build_alerts(
            validated,
            fallback_alerts,
            previous_status,
            status,
            previous_priority,
            priority,
        )
        self._log_result(
            validated, health_score, confidence, previous_status, status,
            previous_priority, priority, used_fallback,
        )

        return HealthResult(
            machine_id=validated.reading.machine_id,
            timestamp=validated.reading.timestamp,
            health_score=health_score,
            machine_status=status,
            confidence_score=confidence,
            trend=trend,
            trend_slope=trend_slope,
            maintenance_priority=priority,
            downtime_risk_pct=downtime_risk,
            production_impact=impact,
            sensor_health=sensor_health,
            sensor_contributions=contributions,
            alerts=alerts,
            used_fallback_values=used_fallback,
        )


    def _check_precondition(self, validated: ValidatedReading) -> None:
        for mapping_name in ("normalized", "deviation"):
            mapping = getattr(validated, mapping_name)
            missing = set(self._config.SENSOR_KEYS) - set(mapping)
            if missing:
                raise AnalysisError(
                    f"ValidatedReading.{mapping_name} is missing sensors "
                    f"{sorted(missing)}; the §3.2 precondition requires all "
                    "sensors to be populated."
                )


    def _resolve_effective_deviations(
        self, validated: ValidatedReading, history: HistoryBuffer
    ) -> Tuple[Dict[str, float], bool, List[str]]:
        if validated.is_valid:
            return dict(validated.deviation), False, []

        flagged_sensors = sorted(
            {
                flag.sensor_key
                for flag in validated.validation_flags
                if flag.sensor_key is not None
            }
        )
        deviations = dict(validated.deviation)
        substituted: List[str] = []
        for key in flagged_sensors:
            deviations[key] = self._last_known_good_deviation(key, history)
            substituted.append(key)

        flag_names = sorted(
            {flag.flag.name for flag in validated.validation_flags}
        )
        if substituted:
            alert = (
                f"Invalid reading at tick {validated.reading.tick} "
                f"({', '.join(flag_names)}): substituted last-known-good "
                f"values for {', '.join(substituted)}."
            )
        else:
            alert = (
                f"Invalid reading at tick {validated.reading.tick} "
                f"({', '.join(flag_names)})."
            )
        self._logger.warning(alert)
        return deviations, True, [alert]

    def _last_known_good_deviation(
        self, key: str, history: HistoryBuffer
    ) -> float:
        for entry_validated, _ in reversed(history.window(len(history))):
            touched = any(
                flag.sensor_key == key
                for flag in entry_validated.validation_flags
            )
            if not touched:
                return entry_validated.deviation[key]
        return 0.0


    def _compute_trend(
        self, history: HistoryBuffer
    ) -> Tuple[TrendDirection, float]:
        scores = [
            result.health_score
            for _, result in history.window(self._config.TREND_WINDOW)
        ]
        if len(scores) < self._config.TREND_MIN_POINTS:
            return TrendDirection.STABLE, 0.0
        slope = float(np.polyfit(range(len(scores)), scores, 1)[0])
        if slope <= self._config.TREND_DEGRADING_SLOPE:
            return TrendDirection.DEGRADING, slope
        if slope >= self._config.TREND_IMPROVING_SLOPE:
            return TrendDirection.IMPROVING, slope
        return TrendDirection.STABLE, slope

    def _trend_penalty(
        self, trend: TrendDirection, slope: float, base_score: float
    ) -> float:
        if trend is not TrendDirection.DEGRADING:
            return 0.0
        penalty = min(
            self._config.TREND_PENALTY_CAP,
            abs(slope) * self._config.TREND_PENALTY_MULTIPLIER,
        )
        return min(penalty, base_score)


    def _status_with_hysteresis(
        self, health_score: float, previous: Optional[MachineStatus]
    ) -> MachineStatus:
        base = self._base_status(health_score)
        if previous is None or base >= previous:
            return base
        candidate = base
        while candidate < previous:
            threshold = self._config.STATUS_THRESHOLDS[candidate.name]
            if health_score >= threshold + self._config.STATUS_HYSTERESIS:
                return candidate
            candidate = MachineStatus(candidate.value + 1)
        return previous

    def _base_status(self, health_score: float) -> MachineStatus:
        if health_score >= self._config.STATUS_THRESHOLDS["HEALTHY"]:
            return MachineStatus.HEALTHY
        if health_score >= self._config.STATUS_THRESHOLDS["WARNING"]:
            return MachineStatus.WARNING
        return MachineStatus.CRITICAL


    def _compute_confidence(
        self,
        validated: ValidatedReading,
        history: HistoryBuffer,
        used_fallback: bool,
    ) -> float:
        window = [
            entry_validated
            for entry_validated, _ in history.window(
                self._config.CONFIDENCE_WINDOW - 1
            )
        ] + [validated]
        n = len(window)

        validity = sum(1 for v in window if v.is_valid) / n
        fill = min(1.0, n / self._config.CONFIDENCE_WINDOW)
        stability = self._signal_stability(window)
        compliance = (
            sum(1 for v in window if not self._has_out_of_range_flag(v)) / n
        )

        weights = self._config.CONFIDENCE_WEIGHTS
        confidence = 100.0 * (
            weights["data_validity"] * validity
            + weights["window_fill"] * fill
            + weights["signal_stability"] * stability
            + weights["range_compliance"] * compliance
        )
        if used_fallback:
            confidence = min(confidence, self._config.FALLBACK_CONFIDENCE_CAP)
        self._logger.debug(
            "confidence components: validity=%.3f fill=%.3f stability=%.3f "
            "compliance=%.3f -> %.1f",
            validity, fill, stability, compliance, confidence,
        )
        return round(confidence, 1)

    def _signal_stability(self, window: List[ValidatedReading]) -> float:
        cvs: List[float] = []
        for key in self._config.SENSOR_KEYS:
            series = [v.normalized[key] for v in window]
            mean = sum(series) / len(series)
            if mean < self._config.STABILITY_MEAN_EXCLUSION:
                continue
            cvs.append(statistics.pstdev(series) / mean)
        if not cvs:
            return 1.0
        mean_cv = sum(cvs) / len(cvs)
        return 1.0 - min(max(mean_cv / self._config.CV_REF, 0.0), 1.0)

    @staticmethod
    def _has_out_of_range_flag(validated: ValidatedReading) -> bool:
        return any(
            flag.flag.name == "OUT_OF_PHYSICAL_RANGE"
            for flag in validated.validation_flags
        )


    def _build_alerts(
        self,
        validated: ValidatedReading,
        fallback_alerts: List[str],
        previous_status: Optional[MachineStatus],
        status: MachineStatus,
        previous_priority: Optional[MaintenancePriority],
        priority: MaintenancePriority,
    ) -> Tuple[str, ...]:
        alerts: List[str] = []
        for flag in validated.validation_flags:
            if flag.sensor_key is None:
                alerts.append(f"{flag.flag.name} on reading.")
            else:
                display = self._config.SENSORS[flag.sensor_key]["display_name"]
                alerts.append(f"{flag.flag.name} on {display}.")
        alerts.extend(fallback_alerts)
        if previous_status is not None and status is not previous_status:
            alerts.append(
                f"Status changed: {previous_status.name} -> {status.name}."
            )
        if (
            previous_priority is not None
            and priority > previous_priority
        ):
            alerts.append(
                "Maintenance priority escalated: "
                f"{previous_priority.name} -> {priority.name}."
            )
        return tuple(alerts)

    def _log_result(
        self,
        validated: ValidatedReading,
        health_score: float,
        confidence: float,
        previous_status: Optional[MachineStatus],
        status: MachineStatus,
        previous_priority: Optional[MaintenancePriority],
        priority: MaintenancePriority,
        used_fallback: bool,
    ) -> None:
        self._logger.debug(
            "tick=%d score=%.1f confidence=%.1f status=%s priority=%s "
            "fallback=%s",
            validated.reading.tick, health_score, confidence, status.name,
            priority.name, used_fallback,
        )
        if previous_status is not None and status is not previous_status:
            self._logger.info(
                "Status transition at tick %d: %s -> %s (score %.1f).",
                validated.reading.tick, previous_status.name, status.name,
                health_score,
            )
        if previous_priority is not None and priority > previous_priority:
            self._logger.info(
                "Priority escalation at tick %d: %s -> %s.",
                validated.reading.tick, previous_priority.name, priority.name,
            )
