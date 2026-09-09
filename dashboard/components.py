
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

import streamlit as st

import config
from models.data_models import MachineStatus

_NO_ALERTS_TEXT = "No active alerts."
COLD_START_VALUE = "—"


def metric_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_color: str = "normal",
) -> None:
    st.metric(label, value, delta=delta, delta_color=delta_color)


def status_badge(status: MachineStatus) -> None:
    color = config.STATUS_COLORS[status.name]
    st.markdown(
        (
            f"<span style='background-color:{color};color:white;"
            "padding:6px 18px;border-radius:16px;font-weight:700;"
            f"font-size:1.05rem;'>{status.name}</span>"
        ),
        unsafe_allow_html=True,
    )


def alert_count_chip(count: int) -> None:
    color = (
        config.STATUS_COLORS["WARNING"]
        if count
        else config.STATUS_COLORS["HEALTHY"]
    )
    label = f"{count} alert{'s' if count != 1 else ''}"
    st.markdown(
        (
            f"<span style='border:1.5px solid {color};color:{color};"
            "padding:3px 12px;border-radius:12px;font-size:0.85rem;'>"
            f"{label}</span>"
        ),
        unsafe_allow_html=True,
    )


def alerts_panel(entries: List[Tuple[datetime, str]]) -> None:
    st.subheader("Alerts")
    if not entries:
        st.caption(_NO_ALERTS_TEXT)
        return
    for timestamp, alert in entries:
        local_time = timestamp.astimezone().strftime("%H:%M:%S")
        st.markdown(f"- `{local_time}` {alert}")
