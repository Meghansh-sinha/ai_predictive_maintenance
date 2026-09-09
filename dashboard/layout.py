
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

import config
from dashboard import charts, components
from models.data_models import (
    AIInsight,
    HealthResult,
    SensorReading,
    SimulationScenario,
)
from utils.history import HistoryBuffer

_PLOTLY_CONFIG = {"displayModeBar": False}
_RESET_PENDING_KEY = "ui_reset_pending"
_AI_REQUESTED_KEY = "ui_ai_requested"


def _request_ai_generation() -> None:
    st.session_state[_AI_REQUESTED_KEY] = True


_PDF_REQUESTED_KEY = "ui_pdf_requested"


def _request_pdf_generation() -> None:
    st.session_state[_PDF_REQUESTED_KEY] = True

_SCENARIO_LABELS = {
    SimulationScenario.NORMAL: "Normal operation",
    SimulationScenario.GRADUAL_DEGRADATION: "Gradual degradation",
    SimulationScenario.RAPID_DEGRADATION: "Rapid degradation",
    SimulationScenario.INTERMITTENT_FAULT: "Intermittent fault",
}

_ABOUT_TEXT = (
    "A locally-run predictive-maintenance demo: simulated industrial "
    "sensor data is validated, scored by a deterministic health engine, "
    "and presented live with AI explanations and PDF reporting."
)
_ARCHITECTURE_TEXT = (
    "Sensor Simulator\n"
    "    → Sensor Interface\n"
    "        → Health Analysis Engine\n"
    "            → Dashboard | Gemini AI | PDF Generator"
)


@dataclass(frozen=True)
class SidebarSelections:

    scenario: SimulationScenario
    auto_run: bool
    refresh_interval_s: float
    step_once: bool
    reset_confirmed: bool
    generate_ai: bool
    generate_pdf: bool




def render_sidebar(state) -> SidebarSelections:
    with st.sidebar:
        st.markdown(f"### {config.MACHINE_NAME}")
        st.caption(config.MACHINE_ID)
        st.divider()

        scenarios = list(SimulationScenario)
        scenario = st.selectbox(
            "Scenario",
            options=scenarios,
            index=scenarios.index(state["scenario"]),
            format_func=lambda s: _SCENARIO_LABELS[s],
            key="ui_scenario",
        )

        auto_run = st.toggle(
            "Auto-run", value=state["auto_run"], key="ui_auto_run"
        )
        refresh_interval_s = st.slider(
            "Refresh interval (s)",
            min_value=config.REFRESH_INTERVAL_MIN_S,
            max_value=config.REFRESH_INTERVAL_MAX_S,
            value=float(state["refresh_interval_s"]),
            step=0.5,
            key="ui_refresh_interval",
        )
        step_once = st.button(
            "Step once", disabled=auto_run, key="ui_step_once"
        )
        reset_confirmed = _render_reset_control()
        st.divider()

        analyzer = state.get("ai_analyzer")
        ai_busy = bool(state.get("ai_busy", False))
        cold_start = len(state["history"]) == 0
        st.button(
            "Generating…" if ai_busy else "Generate AI Analysis",
            disabled=ai_busy or cold_start,
            key="ui_generate_ai",
            on_click=_request_ai_generation,
        )
        generate_ai = bool(st.session_state.pop(_AI_REQUESTED_KEY, False))
        if analyzer is not None and analyzer.is_available():
            st.caption(f"Model: {analyzer.model_name}")
        else:
            st.caption("API key not configured — fallback mode")

        st.button(
            "Generate PDF Report",
            disabled=cold_start,
            key="ui_generate_pdf",
            on_click=_request_pdf_generation,
        )
        generate_pdf = bool(st.session_state.pop(_PDF_REQUESTED_KEY, False))
        last_pdf = state.get("last_pdf_path")
        if last_pdf is not None and Path(last_pdf).exists():
            st.download_button(
                "Download PDF Report",
                data=Path(last_pdf).read_bytes(),
                file_name=Path(last_pdf).name,
                mime="application/pdf",
                key="ui_download_pdf",
            )
            st.caption(Path(last_pdf).name)
        st.divider()

        with st.expander("About"):
            st.write(_ABOUT_TEXT)
            st.text(_ARCHITECTURE_TEXT)

    return SidebarSelections(
        scenario=scenario,
        auto_run=auto_run,
        refresh_interval_s=refresh_interval_s,
        step_once=step_once,
        reset_confirmed=reset_confirmed,
        generate_ai=generate_ai,
        generate_pdf=generate_pdf,
    )


def _render_reset_control() -> bool:
    pending = st.session_state.get(_RESET_PENDING_KEY, False)
    if not pending:
        if st.button("Reset simulation", key="ui_reset_request"):
            st.session_state[_RESET_PENDING_KEY] = True
            st.rerun()
        return False
    confirmed = st.button(
        "Click again to confirm reset", key="ui_reset_confirm", type="primary"
    )
    if st.button("Cancel reset", key="ui_reset_cancel"):
        st.session_state[_RESET_PENDING_KEY] = False
        st.rerun()
    if confirmed:
        st.session_state[_RESET_PENDING_KEY] = False
    return confirmed




def render_dashboard(
    latest_result: Optional[HealthResult],
    latest_reading: Optional[SensorReading],
    history: HistoryBuffer,
    ai_insight: Optional[AIInsight],
) -> None:
    if latest_result is None or len(history) == 0:
        _render_cold_start()
        return

    previous_result = _previous_result(history)
    df = history.to_dataframe()

    _render_status_header(latest_result)
    _render_kpi_cards(latest_result, previous_result)
    _render_gauge_and_contributions(latest_result, previous_result)
    _render_tabs(df)
    components.alerts_panel(_recent_alerts(history))
    _render_ai_insight(latest_result, ai_insight)


def _render_cold_start() -> None:
    st.title(config.PAGE_TITLE)
    st.caption(f"{config.MACHINE_NAME} · {config.MACHINE_ID}")
    columns = st.columns(6)
    for column, label in zip(
        columns,
        (
            "Health Score",
            "Machine Status",
            "Confidence",
            "Maintenance Priority",
            "Downtime Risk",
            "Est. Loss / Day",
        ),
    ):
        with column:
            components.metric_card(label, components.COLD_START_VALUE)
    st.plotly_chart(
        charts.build_collecting_placeholder(),
        use_container_width=True,
        config=_PLOTLY_CONFIG,
    )


def _render_status_header(result: HealthResult) -> None:
    name_col, badge_col, updated_col, chip_col = st.columns([3, 1.2, 1.6, 1])
    with name_col:
        st.markdown(f"## {config.MACHINE_NAME}")
    with badge_col:
        components.status_badge(result.machine_status)
    with updated_col:
        local_time = result.timestamp.astimezone().strftime("%H:%M:%S")
        st.caption(f"Last updated: {local_time}")
    with chip_col:
        components.alert_count_chip(len(result.alerts))


def _render_kpi_cards(
    result: HealthResult, previous: Optional[HealthResult]
) -> None:
    currency = config.CURRENCY_SYMBOL
    loss = result.production_impact.estimated_loss_per_day
    cards = st.columns(6)
    with cards[0]:
        delta = (
            f"{result.health_score - previous.health_score:+.1f}"
            if previous
            else None
        )
        components.metric_card(
            "Health Score", f"{result.health_score:.1f}", delta
        )
    with cards[1]:
        components.metric_card("Machine Status", result.machine_status.name)
    with cards[2]:
        components.metric_card("Confidence", f"{result.confidence_score:.1f}")
    with cards[3]:
        components.metric_card(
            "Maintenance Priority", result.maintenance_priority.name
        )
    with cards[4]:
        delta = (
            f"{result.downtime_risk_pct - previous.downtime_risk_pct:+.1f}%"
            if previous
            else None
        )
        components.metric_card(
            "Downtime Risk",
            f"{result.downtime_risk_pct:.1f}%",
            delta,
            delta_color="inverse",
        )
    with cards[5]:
        delta = (
            f"{loss - previous.production_impact.estimated_loss_per_day:+,.0f}"
            if previous
            else None
        )
        components.metric_card(
            "Est. Loss / Day",
            f"{currency}{loss:,.0f}",
            delta,
            delta_color="inverse",
        )


def _render_gauge_and_contributions(
    result: HealthResult, previous: Optional[HealthResult]
) -> None:
    left, right = st.columns(2)
    previous_score = previous.health_score if previous else None
    with left:
        st.plotly_chart(
            charts.build_health_gauge(result, previous_score),
            use_container_width=True,
            config=_PLOTLY_CONFIG,
        )
    with right:
        st.plotly_chart(
            charts.build_contribution_bar(result),
            use_container_width=True,
            config=_PLOTLY_CONFIG,
        )


def _render_tabs(df: pd.DataFrame) -> None:
    sensors_tab, history_tab, table_tab = st.tabs(
        ["Live Sensors", "Health History", "Data Table"]
    )
    with sensors_tab:
        grid = st.columns(2)
        for index, sensor_key in enumerate(config.SENSOR_KEYS):
            with grid[index % 2]:
                st.plotly_chart(
                    charts.build_sensor_chart(df, sensor_key),
                    use_container_width=True,
                    config=_PLOTLY_CONFIG,
                )
    with history_tab:
        st.plotly_chart(
            charts.build_health_history(df),
            use_container_width=True,
            config=_PLOTLY_CONFIG,
        )
        st.plotly_chart(
            charts.build_risk_history(df),
            use_container_width=True,
            config=_PLOTLY_CONFIG,
        )
    with table_tab:
        st.dataframe(
            _format_table(df.tail(config.DATA_TABLE_ROWS)),
            use_container_width=True,
            hide_index=True,
        )


def _format_table(df: pd.DataFrame) -> pd.DataFrame:
    formatted = df.copy()
    local_tz = datetime.now().astimezone().tzinfo
    formatted["timestamp"] = (
        formatted["timestamp"].dt.tz_convert(local_tz).dt.strftime("%H:%M:%S")
    )
    float_columns = formatted.select_dtypes(include="float").columns
    formatted[float_columns] = formatted[float_columns].round(1)
    return formatted


def _recent_alerts(history: HistoryBuffer) -> List[Tuple[object, str]]:
    collected: List[Tuple[object, str]] = []
    for _, result in reversed(history.window(len(history))):
        for alert in reversed(result.alerts):
            collected.append((result.timestamp, alert))
            if len(collected) >= config.ALERTS_PANEL_MAX:
                return collected
    return collected


def _previous_result(history: HistoryBuffer) -> Optional[HealthResult]:
    window = history.window(2)
    if len(window) < 2:
        return None
    return window[0][1]


def _render_ai_insight(
    result: HealthResult, ai_insight: Optional[AIInsight]
) -> None:
    if ai_insight is None:
        return
    st.subheader("AI Insight")
    if ai_insight.is_fallback:
        st.caption("🔌 Fallback (offline) analysis")
    st.write(ai_insight.summary)
    causes_col, actions_col = st.columns(2)
    with causes_col:
        st.markdown("**Probable causes**")
        for cause in ai_insight.probable_causes:
            st.markdown(f"- {cause}")
    with actions_col:
        st.markdown("**Recommended actions**")
        for action in ai_insight.recommended_actions:
            st.markdown(f"- {action}")
    st.write(ai_insight.urgency_note)
    generated_local = ai_insight.generated_at.astimezone().strftime("%H:%M:%S")
    st.caption(f"Generated by {ai_insight.model_name} at {generated_local}")
    if (
        abs(ai_insight.source_health_score - result.health_score)
        > config.AI_STALENESS_SCORE_DELTA
    ):
        st.caption("⚠ Insight may be outdated — regenerate.")
