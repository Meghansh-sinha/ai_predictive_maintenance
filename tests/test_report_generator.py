
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import config
from ai.gemini_client import build_fallback_insight
from health_engine import HealthAnalysisEngine
from models.data_models import AIInsight, SimulationScenario
from pdf import PDFReportGenerator
from sensor_interface import SensorInterface
from simulator import SensorSimulator
from utils.history import HistoryBuffer

logging.disable(logging.WARNING)

_FILENAME_REGEX = re.compile(
    r"^maintenance_report_" + re.escape(config.MACHINE_ID) + r"_\d{8}_\d{6}\.pdf$"
)


def build_history(
    ticks: int, scenario: SimulationScenario = SimulationScenario.NORMAL
) -> HistoryBuffer:
    simulator = SensorSimulator(config, seed=42)
    simulator.set_scenario(scenario)
    interface = SensorInterface(config)
    engine = HealthAnalysisEngine(config)
    history = HistoryBuffer(config.HISTORY_MAX_LEN)
    for _ in range(ticks):
        validated = interface.process(simulator.generate_reading())
        result = engine.analyze(validated, history)
        history.append(validated, result)
    return history


def generate(
    tmp_path: Path,
    monkeypatch: Any,
    history: HistoryBuffer,
    insight: Optional[AIInsight],
) -> Path:
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path))
    generator = PDFReportGenerator(config)
    latest_result = history.latest()[1]
    return generator.generate(latest_result, history, insight)




def test_generates_with_full_data_and_insight(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history = build_history(120, SimulationScenario.RAPID_DEGRADATION)
    insight = build_fallback_insight(
        history.latest()[1], history.summary(), config
    )
    path = generate(tmp_path, monkeypatch, history, insight)
    assert path.exists()
    assert path.parent == tmp_path
    assert path.stat().st_size > 0
    assert path.read_bytes()[:5] == b"%PDF-"
    assert not list(tmp_path.glob("*.tmp"))




def test_generates_with_ai_insight_none(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history = build_history(30)
    path = generate(tmp_path, monkeypatch, history, None)
    assert path.exists()
    assert path.stat().st_size > 0
    assert path.read_bytes()[:5] == b"%PDF-"




def test_generates_with_minimal_one_tick_history(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history = build_history(1)
    path = generate(tmp_path, monkeypatch, history, None)
    assert path.exists()
    assert path.stat().st_size > 0
    assert path.read_bytes()[:5] == b"%PDF-"




def test_filename_matches_configured_pattern(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history = build_history(10)
    path = generate(tmp_path, monkeypatch, history, None)
    assert _FILENAME_REGEX.match(path.name), path.name




def test_returns_path_and_supports_stale_insight_exec_summary(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history = build_history(40)
    latest_result = history.latest()[1]
    stale = build_fallback_insight(latest_result, history.summary(), config)
    stale = AIInsight(
        summary=stale.summary,
        probable_causes=stale.probable_causes,
        recommended_actions=stale.recommended_actions,
        urgency_note=stale.urgency_note,
        model_name=stale.model_name,
        generated_at=stale.generated_at,
        is_fallback=stale.is_fallback,
        source_health_score=latest_result.health_score
        + config.AI_STALENESS_SCORE_DELTA
        + 10.0,
    )
    path = generate(tmp_path, monkeypatch, history, stale)
    assert isinstance(path, Path)
    assert path.read_bytes()[:5] == b"%PDF-"


def test_generation_is_reasonably_fast(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import time

    history = build_history(200, SimulationScenario.GRADUAL_DEGRADATION)
    started = time.monotonic()
    generate(tmp_path, monkeypatch, history, None)
    assert time.monotonic() - started < 2.0
