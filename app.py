
from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

import config
from ai import GeminiAnalyzer
from dashboard import layout
from health_engine import HealthAnalysisEngine
from models.data_models import SimulationScenario
from pdf import PDFReportGenerator
from sensor_interface import SensorInterface
from simulator import SensorSimulator
from utils.exceptions import (
    ConfigurationError,
    PMDashboardError,
    ReportGenerationError,
)
from utils.history import HistoryBuffer
from utils.logger import get_logger, setup_logging

_GENERIC_ERROR_BANNER = "An internal error occurred — see logs."


def _initialize_session() -> None:
    if st.session_state.get("initialized", False):
        return

    load_dotenv()
    setup_logging()
    logger = get_logger(__name__)

    try:
        config.validate_config()
    except ConfigurationError as exc:
        logger.error("Startup configuration validation failed: %s", exc)
        st.error(str(exc))
        st.stop()

    st.session_state["simulator"] = SensorSimulator(config, seed=None)
    st.session_state["interface"] = SensorInterface(config)
    st.session_state["engine"] = HealthAnalysisEngine(config)
    st.session_state["history"] = HistoryBuffer(config.HISTORY_MAX_LEN)
    st.session_state["scenario"] = SimulationScenario.NORMAL
    st.session_state["auto_run"] = True
    st.session_state["refresh_interval_s"] = config.TICK_INTERVAL_S
    st.session_state["ai_insight"] = None
    st.session_state["ai_busy"] = False
    st.session_state["last_pdf_path"] = None
    st.session_state["last_error_banner"] = None
    st.session_state["ai_analyzer"] = GeminiAnalyzer(config)
    st.session_state["initialized"] = True
    logger.info(
        "Session initialized for %s (%s).", config.MACHINE_NAME, config.MACHINE_ID
    )


def _apply_selections(selections: layout.SidebarSelections) -> None:
    state = st.session_state
    if selections.scenario is not state["scenario"]:
        state["scenario"] = selections.scenario
        state["simulator"].set_scenario(selections.scenario)
    state["auto_run"] = selections.auto_run
    state["refresh_interval_s"] = selections.refresh_interval_s
    if selections.reset_confirmed:
        _reset_simulation()


def _generate_ai_insight() -> None:
    state = st.session_state
    latest = state["history"].latest()
    if latest is None:
        return
    previous = state["ai_insight"]
    state["ai_busy"] = True
    try:
        with st.spinner("Generating AI analysis…"):
            insight = state["ai_analyzer"].generate_insight(
                latest[1], state["history"].summary()
            )
    finally:
        state["ai_busy"] = False
    if previous is not None and insight.generated_at == previous.generated_at:
        st.toast("Reused recent analysis.")
    else:
        st.toast("AI analysis ready — see the AI Insight panel below.")
    state["ai_insight"] = insight


def _generate_pdf_report() -> None:
    state = st.session_state
    latest = state["history"].latest()
    if latest is None:
        return
    try:
        with st.spinner("Generating PDF report…"):
            path = PDFReportGenerator(config).generate(
                latest[1], state["history"], state["ai_insight"]
            )
    except ReportGenerationError as exc:
        st.error(str(exc))
        return
    state["last_pdf_path"] = path
    st.rerun()


def _reset_simulation() -> None:
    state = st.session_state
    state["history"] = HistoryBuffer(config.HISTORY_MAX_LEN)
    state["simulator"].reset()
    state["ai_insight"] = None
    state["last_pdf_path"] = None
    state["ui_cold_start_synced"] = False
    get_logger(__name__).info("Simulation reset by operator.")


def _do_tick() -> None:
    state = st.session_state
    reading = state["simulator"].generate_reading()
    validated = state["interface"].process(reading)
    result = state["engine"].analyze(validated, state["history"])
    state["history"].append(validated, result)
    state["last_error_banner"] = None


def _run_tick_safely(tick_due: bool) -> None:
    if not tick_due:
        return
    logger = get_logger(__name__)
    try:
        _do_tick()
    except PMDashboardError as exc:
        logger.error("Tick pipeline error: %s", exc)
        st.session_state["last_error_banner"] = str(exc)
    except Exception:
        logger.exception("Unexpected error in tick pipeline.")
        st.session_state["last_error_banner"] = _GENERIC_ERROR_BANNER


def main() -> None:
    st.set_page_config(
        page_title=config.PAGE_TITLE,
        page_icon=config.PAGE_ICON,
        layout=config.PAGE_LAYOUT,
    )
    _initialize_session()

    selections = layout.render_sidebar(st.session_state)
    _apply_selections(selections)
    step_requested = selections.step_once
    if selections.generate_ai:
        _generate_ai_insight()
    if selections.generate_pdf:
        _generate_pdf_report()

    run_every = (
        st.session_state["refresh_interval_s"]
        if st.session_state["auto_run"]
        else None
    )

    @st.fragment(run_every=run_every)
    def _live_section() -> None:
        _run_tick_safely(st.session_state["auto_run"] or step_requested)
        history: HistoryBuffer = st.session_state["history"]
        if len(history) > 0 and not st.session_state.get(
            "ui_cold_start_synced", False
        ):
            st.session_state["ui_cold_start_synced"] = True
            st.rerun(scope="app")
        if st.session_state["last_error_banner"]:
            st.error(st.session_state["last_error_banner"])
        latest = history.latest()
        layout.render_dashboard(
            latest_result=latest[1] if latest else None,
            latest_reading=latest[0].reading if latest else None,
            history=history,
            ai_insight=st.session_state["ai_insight"],
        )

    _live_section()


main()
