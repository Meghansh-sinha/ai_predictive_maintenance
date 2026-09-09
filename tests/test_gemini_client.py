
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import config
from ai.gemini_client import (
    GeminiAnalyzer,
    build_fallback_insight,
    parse_insight_payload,
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

_VALID_PAYLOAD: Dict[str, Any] = {
    "summary": "Vibration is elevated and trending worse.",
    "probable_causes": ["Bearing wear.", "Misalignment."],
    "recommended_actions": ["Inspect bearings.", "Check alignment."],
    "urgency_note": "Prompt action advised.",
}


def make_result(
    *,
    health_score: float = 72.5,
    status: MachineStatus = MachineStatus.WARNING,
    priority: MaintenancePriority = MaintenancePriority.HIGH,
    trend: TrendDirection = TrendDirection.DEGRADING,
    contributions: Optional[Dict[str, float]] = None,
) -> HealthResult:
    return HealthResult(
        machine_id=config.MACHINE_ID,
        timestamp=_T0,
        health_score=health_score,
        machine_status=status,
        confidence_score=88.0,
        trend=trend,
        trend_slope=-0.32,
        maintenance_priority=priority,
        downtime_risk_pct=41.2,
        production_impact=ProductionImpact(49.4, 53395.2, "High"),
        sensor_health={key: 80.0 for key in config.SENSOR_KEYS},
        sensor_contributions=(
            contributions
            if contributions is not None
            else {
                "vibration_mm_s": 14.0,
                "temperature_c": 9.0,
                "pressure_bar": 1.0,
                "current_a": 0.0,
            }
        ),
        alerts=(),
        used_fallback_values=False,
    )


def make_summary() -> HistorySummary:
    return HistorySummary(
        window_length=100,
        start_time=_T0,
        end_time=_T0,
        health_min=70.0,
        health_mean=85.0,
        health_max=100.0,
        health_delta=-27.5,
        sensor_stats={
            key: {"min": 1.0, "mean": 2.0, "max": 3.0}
            for key in config.SENSOR_KEYS
        },
        invalid_count=2,
        critical_count=0,
    )


class FakeClient:

    def __init__(self, outcomes: List[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **_: Any) -> Any:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def make_analyzer(outcomes: List[Any]) -> "tuple[GeminiAnalyzer, FakeClient]":
    fake = FakeClient(outcomes)
    analyzer = GeminiAnalyzer(config, client_factory=lambda: fake)
    return analyzer, fake


def patch_backoff(monkeypatch: Any) -> None:
    import ai.gemini_client as module

    monkeypatch.setattr(module.time, "sleep", lambda _: None)




def test_parse_valid_json() -> None:
    parsed = parse_insight_payload(json.dumps(_VALID_PAYLOAD))
    assert parsed["summary"] == _VALID_PAYLOAD["summary"]
    assert parsed["probable_causes"] == tuple(_VALID_PAYLOAD["probable_causes"])
    assert parsed["recommended_actions"] == tuple(
        _VALID_PAYLOAD["recommended_actions"]
    )
    assert parsed["urgency_note"] == _VALID_PAYLOAD["urgency_note"]


def test_parse_strips_markdown_fences() -> None:
    fenced = "```json\n" + json.dumps(_VALID_PAYLOAD) + "\n```"
    parsed = parse_insight_payload(fenced)
    assert parsed["summary"] == _VALID_PAYLOAD["summary"]


def test_parse_missing_key_raises() -> None:
    broken = {k: v for k, v in _VALID_PAYLOAD.items() if k != "urgency_note"}
    try:
        parse_insight_payload(json.dumps(broken))
    except ValueError as exc:
        assert "urgency_note" in str(exc)
    else:
        raise AssertionError("missing key must raise ValueError")


def test_parse_wrong_type_raises() -> None:
    broken = dict(_VALID_PAYLOAD, probable_causes="not-a-list")
    try:
        parse_insight_payload(json.dumps(broken))
    except ValueError as exc:
        assert "probable_causes" in str(exc)
    else:
        raise AssertionError("wrong type must raise ValueError")


def test_parse_clips_over_long_arrays() -> None:
    oversized = dict(
        _VALID_PAYLOAD,
        probable_causes=[f"cause {i}" for i in range(10)],
        recommended_actions=[f"action {i}" for i in range(10)],
    )
    parsed = parse_insight_payload(json.dumps(oversized))
    assert len(parsed["probable_causes"]) == 4
    assert len(parsed["recommended_actions"]) == 5


def test_parse_garbage_raises() -> None:
    for garbage in ("", "   ", "not json at all", "[1, 2, 3]"):
        try:
            parse_insight_payload(garbage)
        except (ValueError, json.JSONDecodeError):
            continue
        raise AssertionError(f"garbage {garbage!r} must raise")




def test_fallback_cause_ordering_follows_contributions() -> None:
    result = make_result(
        contributions={
            "pressure_bar": 12.0,
            "current_a": 8.0,
            "temperature_c": 2.0,
            "vibration_mm_s": 0.0,
        }
    )
    insight = build_fallback_insight(result, make_summary(), config)
    assert insight.is_fallback is True
    assert insight.model_name == config.AI_FALLBACK_MODEL_NAME
    assert insight.probable_causes == (
        "Suction restriction or impeller wear.",
        "Increased mechanical load or winding issue.",
        "Cooling degradation or friction heating.",
    )


def test_fallback_action_set_matches_priority_level() -> None:
    for priority in MaintenancePriority:
        result = make_result(priority=priority)
        insight = build_fallback_insight(result, make_summary(), config)
        assert len(insight.recommended_actions) >= 2
        assert priority.name in insight.urgency_note
        if priority is MaintenancePriority.URGENT:
            assert any("immediate" in a.lower() for a in insight.recommended_actions)
        if priority is MaintenancePriority.LOW:
            assert any("routine" in a.lower() for a in insight.recommended_actions)


def test_fallback_with_no_contributions_reports_nominal() -> None:
    result = make_result(
        health_score=100.0,
        status=MachineStatus.HEALTHY,
        priority=MaintenancePriority.LOW,
        trend=TrendDirection.STABLE,
        contributions={key: 0.0 for key in config.SENSOR_KEYS},
    )
    insight = build_fallback_insight(result, make_summary(), config)
    assert insight.probable_causes == ("No abnormal sensor behavior detected.",)
    assert insight.source_health_score == 100.0




def test_success_path_returns_parsed_insight() -> None:
    analyzer, fake = make_analyzer([json.dumps(_VALID_PAYLOAD)])
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is False
    assert insight.summary == _VALID_PAYLOAD["summary"]
    assert insight.source_health_score == 72.5
    assert fake.calls == 1


def test_transient_failure_then_success_uses_retry(monkeypatch: Any) -> None:
    patch_backoff(monkeypatch)
    analyzer, fake = make_analyzer(
        [TimeoutError("slow"), json.dumps(_VALID_PAYLOAD)]
    )
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is False
    assert fake.calls == 2


def test_persistent_failure_routes_to_fallback(monkeypatch: Any) -> None:
    patch_backoff(monkeypatch)
    analyzer, fake = make_analyzer([TimeoutError("a"), TimeoutError("b")])
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is True
    assert fake.calls == 1 + config.AI_MAX_RETRIES


def test_non_transient_error_falls_back_without_retry() -> None:
    auth_error = type("AuthError", (Exception,), {})()
    auth_error.code = 401
    analyzer, fake = make_analyzer([auth_error, json.dumps(_VALID_PAYLOAD)])
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is True
    assert fake.calls == 1


def test_parse_failure_consumes_retry_then_falls_back(
    monkeypatch: Any,
) -> None:
    patch_backoff(monkeypatch)
    analyzer, fake = make_analyzer(["not json", "still not json"])
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is True
    assert fake.calls == 2


def test_missing_api_key_falls_back_without_calling_transport(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    analyzer = GeminiAnalyzer(config)
    assert analyzer.is_available() is False
    insight = analyzer.generate_insight(make_result(), make_summary())
    assert insight.is_fallback is True
    assert insight.model_name == config.AI_FALLBACK_MODEL_NAME


def test_cache_hit_returns_same_insight_without_second_call() -> None:
    analyzer, fake = make_analyzer(
        [json.dumps(_VALID_PAYLOAD), json.dumps(_VALID_PAYLOAD)]
    )
    result = make_result()
    first = analyzer.generate_insight(result, make_summary())
    second = analyzer.generate_insight(result, make_summary())
    assert second is first
    assert fake.calls == 1


def test_cache_misses_when_key_metrics_change() -> None:
    analyzer, fake = make_analyzer(
        [json.dumps(_VALID_PAYLOAD), json.dumps(_VALID_PAYLOAD)]
    )
    analyzer.generate_insight(make_result(health_score=72.5), make_summary())
    analyzer.generate_insight(make_result(health_score=60.0), make_summary())
    assert fake.calls == 2


def test_model_name_env_override(monkeypatch: Any) -> None:
    analyzer, _ = make_analyzer([json.dumps(_VALID_PAYLOAD)])
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-override")
    assert analyzer.model_name == "gemini-test-override"
    monkeypatch.delenv("GEMINI_MODEL")
    assert analyzer.model_name == config.GEMINI_MODEL_DEFAULT
