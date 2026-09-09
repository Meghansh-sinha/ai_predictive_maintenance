
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai.prompt_builder import (
    MAX_PROBABLE_CAUSES,
    MAX_RECOMMENDED_ACTIONS,
    build_analysis_prompt,
)
from models.data_models import (
    AIInsight,
    HealthResult,
    HistorySummary,
    MachineStatus,
    MaintenancePriority,
)
from utils.logger import get_logger

_API_KEY_ENV = "GEMINI_API_KEY"
_MODEL_ENV = "GEMINI_MODEL"

_REQUIRED_KEYS = (
    "summary",
    "probable_causes",
    "recommended_actions",
    "urgency_note",
)

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_NON_TRANSIENT_STATUS_CODES = {400, 401, 403, 404}


_CAUSE_TABLE: Dict[str, str] = {
    "vibration_mm_s": "Possible bearing wear or shaft misalignment.",
    "temperature_c": "Cooling degradation or friction heating.",
    "pressure_bar": "Suction restriction or impeller wear.",
    "current_a": "Increased mechanical load or winding issue.",
}
_NO_CAUSE_TEXT = "No abnormal sensor behavior detected."

_SUMMARY_TEMPLATES: Dict[str, str] = {
    MachineStatus.HEALTHY.name: (
        "{machine} is operating normally with a health score of {score} "
        "and a {trend} trend. No significant sensor deviations are "
        "present. Confidence in this assessment is {confidence}."
    ),
    MachineStatus.WARNING.name: (
        "{machine} shows degraded condition with a health score of "
        "{score} and a {trend} trend. The dominant contributor is "
        "{dominant}. Confidence in this assessment is {confidence}."
    ),
    MachineStatus.CRITICAL.name: (
        "{machine} is in a critical condition with a health score of "
        "{score} and a {trend} trend. The dominant contributor is "
        "{dominant}. Immediate attention is required. Confidence in this "
        "assessment is {confidence}."
    ),
}

_ACTION_TABLE: Dict[str, Tuple[str, ...]] = {
    MaintenancePriority.LOW.name: (
        "Continue routine monitoring.",
        "Review sensor trends at the next scheduled check.",
    ),
    MaintenancePriority.MEDIUM.name: (
        "Schedule an inspection within the next maintenance window.",
        "Increase monitoring of the dominant sensors.",
        "Verify lubrication and cooling as a precaution.",
    ),
    MaintenancePriority.HIGH.name: (
        "Plan corrective maintenance within 24-48 hours.",
        "Increase monitoring frequency on the dominant sensors.",
        "Stage replacement parts for the suspected components.",
    ),
    MaintenancePriority.URGENT.name: (
        "Arrange immediate shutdown and inspection.",
        "Dispatch the maintenance team now.",
        "Isolate the machine from production if symptoms escalate.",
        "Verify safety interlocks before intervention.",
    ),
}

_URGENCY_TEMPLATE = (
    "With {priority} maintenance priority and a {risk}% downtime risk, "
    "{clause}"
)
_URGENCY_CLAUSES: Dict[str, str] = {
    MaintenancePriority.LOW.name: "no immediate action is required.",
    MaintenancePriority.MEDIUM.name: (
        "action should be planned for the next maintenance window."
    ),
    MaintenancePriority.HIGH.name: "prompt corrective action is advised.",
    MaintenancePriority.URGENT.name: "immediate intervention is required.",
}




def parse_insight_payload(text: Optional[str]) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("Empty model response.")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Model response is not a JSON object.")
    for key in _REQUIRED_KEYS:
        if key not in payload:
            raise ValueError(f"Model response is missing key {key!r}.")
    if not isinstance(payload["summary"], str) or not payload["summary"]:
        raise ValueError("summary must be a non-empty string.")
    if not isinstance(payload["urgency_note"], str):
        raise ValueError("urgency_note must be a string.")
    for key in ("probable_causes", "recommended_actions"):
        value = payload[key]
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"{key} must be an array of strings.")
    return {
        "summary": payload["summary"].strip(),
        "probable_causes": tuple(
            payload["probable_causes"][:MAX_PROBABLE_CAUSES]
        ),
        "recommended_actions": tuple(
            payload["recommended_actions"][:MAX_RECOMMENDED_ACTIONS]
        ),
        "urgency_note": payload["urgency_note"].strip(),
    }




def build_fallback_insight(
    result: HealthResult, history_summary: HistorySummary, config: ModuleType
) -> AIInsight:
    contributing = sorted(
        (
            (key, value)
            for key, value in result.sensor_contributions.items()
            if key in _CAUSE_TABLE and value > 0.0
        ),
        key=lambda kv: kv[1],
        reverse=True,
    )
    causes = tuple(
        _CAUSE_TABLE[key] for key, _ in contributing[:MAX_PROBABLE_CAUSES]
    ) or (_NO_CAUSE_TEXT,)
    dominant = (
        config.SENSORS[contributing[0][0]]["display_name"]
        if contributing
        else "none"
    )

    summary = _SUMMARY_TEMPLATES[result.machine_status.name].format(
        machine=config.MACHINE_NAME,
        score=f"{result.health_score:.1f}",
        trend=result.trend.value.lower(),
        dominant=dominant,
        confidence=f"{result.confidence_score:.1f}",
    )
    urgency_note = _URGENCY_TEMPLATE.format(
        priority=result.maintenance_priority.name,
        risk=f"{result.downtime_risk_pct:.1f}",
        clause=_URGENCY_CLAUSES[result.maintenance_priority.name],
    )
    return AIInsight(
        summary=summary,
        probable_causes=causes,
        recommended_actions=_ACTION_TABLE[result.maintenance_priority.name][
            :MAX_RECOMMENDED_ACTIONS
        ],
        urgency_note=urgency_note,
        model_name=config.AI_FALLBACK_MODEL_NAME,
        generated_at=datetime.now(timezone.utc),
        is_fallback=True,
        source_health_score=result.health_score,
    )




class GeminiAnalyzer:

    def __init__(
        self,
        config: ModuleType,
        client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._logger = get_logger(__name__)
        self._client: Optional[Any] = None
        self._cache: Optional[Tuple[Tuple[Any, ...], AIInsight]] = None

    @property
    def model_name(self) -> str:
        return os.environ.get(_MODEL_ENV) or self._config.GEMINI_MODEL_DEFAULT

    def is_available(self) -> bool:
        if self._client_factory is not None:
            return True
        return bool(os.environ.get(_API_KEY_ENV))


    def generate_insight(
        self, result: HealthResult, history_summary: HistorySummary
    ) -> AIInsight:
        cache_key = self._cache_key(result)
        if self._cache is not None and self._cache[0] == cache_key:
            self._logger.info("Reused recent analysis (cache hit, §10.5).")
            return self._cache[1]

        if not self.is_available():
            self._logger.warning(
                "Fallback engaged: %s not configured.", _API_KEY_ENV
            )
            return build_fallback_insight(result, history_summary, self._config)

        prompt = build_analysis_prompt(result, history_summary, self._config)
        self._logger.debug("Prompt length: %d characters.", len(prompt))

        payload = self._request_with_retry(prompt)
        if payload is None:
            return build_fallback_insight(result, history_summary, self._config)

        insight = AIInsight(
            summary=payload["summary"],
            probable_causes=payload["probable_causes"],
            recommended_actions=payload["recommended_actions"],
            urgency_note=payload["urgency_note"],
            model_name=self.model_name,
            generated_at=datetime.now(timezone.utc),
            is_fallback=False,
            source_health_score=result.health_score,
        )
        self._cache = (cache_key, insight)
        return insight


    @staticmethod
    def _cache_key(result: HealthResult) -> Tuple[Any, ...]:
        return (
            round(result.health_score, 1),
            result.machine_status.name,
            result.maintenance_priority.name,
            result.trend.value,
        )

    def _request_with_retry(self, prompt: str) -> Optional[Dict[str, Any]]:
        attempts = 1 + self._config.AI_MAX_RETRIES
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                text = self._call_model(prompt)
                payload = parse_insight_payload(text)
            except ValueError as exc:
                self._log_attempt_failure(attempt, attempts, exc)
                if attempt == attempts:
                    break
                time.sleep(self._config.AI_RETRY_BACKOFF_S)
                continue
            except Exception as exc:
                if not self._is_transient(exc) or attempt == attempts:
                    self._logger.warning(
                        "Fallback engaged after %s.", type(exc).__name__
                    )
                    break
                self._log_attempt_failure(attempt, attempts, exc)
                time.sleep(self._config.AI_RETRY_BACKOFF_S)
                continue
            latency = time.monotonic() - started
            self._logger.debug("Response latency: %.2fs.", latency)
            self._logger.info(
                "Insight generated (model=%s, latency=%.2fs).",
                self.model_name,
                latency,
            )
            return payload
        return None

    def _log_attempt_failure(
        self, attempt: int, attempts: int, exc: Exception
    ) -> None:
        self._logger.warning(
            "AI attempt %d/%d failed (%s); %s.",
            attempt,
            attempts,
            type(exc).__name__,
            "retrying" if attempt < attempts else "no retries left",
        )

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        status = getattr(exc, "code", None) or getattr(
            exc, "status_code", None
        )
        if isinstance(status, int):
            if status in _NON_TRANSIENT_STATUS_CODES:
                return False
            return status in _TRANSIENT_STATUS_CODES
        return True

    def _call_model(self, prompt: str) -> Optional[str]:
        client = self._get_client()
        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "temperature": self._config.AI_TEMPERATURE,
                "max_output_tokens": self._config.AI_MAX_OUTPUT_TOKENS,
            },
        )
        return getattr(response, "text", None)

    def _get_client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                self._client = self._create_sdk_client()
        return self._client

    def _create_sdk_client(self) -> Any:
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=os.environ.get(_API_KEY_ENV),
            http_options=types.HttpOptions(
                timeout=int(self._config.AI_REQUEST_TIMEOUT_S * 1000)
            ),
        )
