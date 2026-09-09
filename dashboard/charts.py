
from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd
import plotly.graph_objects as go

import config
from models.data_models import HealthResult, MachineStatus

_CONTRIBUTION_TITLE = "What is driving the score down"
_ALL_NOMINAL_TEXT = "All sensors nominal"
_COLLECTING_TEXT = "Collecting data…"
_TREND_PENALTY_LABEL = "Degrading trend"
_NOMINAL_CONTRIBUTION_THRESHOLD = 1.0

_TRANSPARENT = "rgba(0,0,0,0)"


def _apply_base_layout(fig: go.Figure, title: Optional[str] = None) -> go.Figure:
    fig.update_layout(
        template=config.PLOTLY_TEMPLATE,
        paper_bgcolor=_TRANSPARENT,
        plot_bgcolor=_TRANSPARENT,
        font={"size": 12},
        margin={"l": 45, "r": 20, "t": 45 if title else 25, "b": 35},
        title=title,
        showlegend=False,
    )
    return fig


def _status_zones() -> tuple:
    warning = config.STATUS_THRESHOLDS["WARNING"]
    healthy = config.STATUS_THRESHOLDS["HEALTHY"]
    return (
        (0.0, warning, config.STATUS_COLORS["CRITICAL"]),
        (warning, healthy, config.STATUS_COLORS["WARNING"]),
        (healthy, 100.0, config.STATUS_COLORS["HEALTHY"]),
    )




def build_health_gauge(
    result: HealthResult, previous_score: Optional[float] = None
) -> go.Figure:
    mode = "gauge+number" + ("+delta" if previous_score is not None else "")
    indicator = go.Indicator(
        mode=mode,
        value=result.health_score,
        number={"valueformat": ".1f"},
        delta=(
            {"reference": previous_score, "valueformat": ".1f"}
            if previous_score is not None
            else None
        ),
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": config.STATUS_COLORS[result.machine_status.name]},
            "steps": [
                {"range": [lower, upper], "color": color}
                for lower, upper, color in _status_zones()
            ],
            "threshold": {
                "line": {"color": "#333333", "width": 3},
                "thickness": 0.85,
                "value": result.health_score,
            },
        },
    )
    fig = go.Figure(indicator)
    fig.update_layout(height=280)
    return _apply_base_layout(fig)




def build_health_history(df: pd.DataFrame) -> go.Figure:
    current_status = df["machine_status"].iloc[-1]
    fig = go.Figure(
        go.Scatter(
            x=df["timestamp"],
            y=df["health_score"],
            mode="lines",
            line={"color": config.STATUS_COLORS[current_status], "width": 2},
            customdata=df[["machine_status", "confidence_score"]],
            hovertemplate=(
                "%{x|%H:%M:%S}<br>Score: %{y:.1f}"
                "<br>Status: %{customdata[0]}"
                "<br>Confidence: %{customdata[1]:.1f}<extra></extra>"
            ),
        )
    )
    for lower, upper, color in _status_zones():
        fig.add_hrect(
            y0=lower,
            y1=upper,
            fillcolor=color,
            opacity=config.STATUS_BAND_OPACITY,
            line_width=0,
        )
    fig.update_yaxes(range=[0, 100], title_text="Health score")
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_layout(height=300, hovermode="x unified")
    return _apply_base_layout(fig)




def build_sensor_chart(df: pd.DataFrame, sensor_key: str) -> go.Figure:
    spec = config.SENSORS[sensor_key]
    fig = go.Figure(
        go.Scatter(
            x=df["timestamp"],
            y=df[sensor_key],
            mode="lines",
            line={"width": 2},
            name=spec["display_name"],
            hovertemplate="%{x|%H:%M:%S}<br>%{y:.2f}<extra></extra>",
        )
    )
    n_lo, n_hi = spec["nominal_band"]
    fig.add_hrect(
        y0=n_lo,
        y1=n_hi,
        fillcolor=config.STATUS_COLORS["HEALTHY"],
        opacity=config.STATUS_BAND_OPACITY,
        line_width=0,
    )
    for w_lo, w_hi in spec["warning_bands"]:
        fig.add_hrect(
            y0=w_lo,
            y1=w_hi,
            fillcolor=config.STATUS_COLORS["WARNING"],
            opacity=config.STATUS_BAND_OPACITY,
            line_width=0,
        )
    for bound in (spec["critical_low"], spec["critical_high"]):
        if bound is not None:
            fig.add_hline(
                y=bound,
                line={
                    "color": config.STATUS_COLORS["CRITICAL"],
                    "dash": "dash",
                    "width": 1.5,
                },
            )
    flagged = df[df[f"{sensor_key}_flagged"]]
    if not flagged.empty:
        fig.add_trace(
            go.Scatter(
                x=flagged["timestamp"],
                y=flagged[sensor_key],
                mode="markers",
                marker={
                    "color": config.STATUS_COLORS["CRITICAL"],
                    "size": 7,
                    "symbol": "x",
                },
                name="Flagged",
                hovertemplate="Flagged: %{y:.2f}<extra></extra>",
            )
        )
    fig.update_yaxes(
        title_text=f"{spec['display_name']} ({spec['unit']})"
    )
    fig.update_layout(height=240, hovermode="x unified")
    return _apply_base_layout(fig)




def build_contribution_bar(result: HealthResult) -> go.Figure:

    def _label(key: str) -> str:
        if key == "trend_penalty":
            return _TREND_PENALTY_LABEL
        return config.SENSORS[key]["display_name"]

    items = sorted(
        result.sensor_contributions.items(), key=lambda kv: kv[1], reverse=True
    )
    labels = [_label(key) for key, _ in items]
    values = [value for _, value in items]
    total = sum(values)

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            text=[f"{value:.1f} pts" for value in values],
            textposition="outside",
            marker={
                "color": values,
                "colorscale": [
                    [0.0, config.STATUS_COLORS["HEALTHY"]],
                    [1.0, config.STATUS_COLORS["CRITICAL"]],
                ],
                "cmin": 0.0,
                "cmax": max(max(values), 1.0) if values else 1.0,
            },
            hovertemplate="%{y}: %{x:.1f} pts<extra></extra>",
        )
    )
    if total < _NOMINAL_CONTRIBUTION_THRESHOLD:
        fig.add_annotation(
            text=_ALL_NOMINAL_TEXT,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": config.STATUS_COLORS["HEALTHY"]},
        )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Contribution (points)")
    fig.update_layout(height=280)
    return _apply_base_layout(fig, title=_CONTRIBUTION_TITLE)




def build_risk_history(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=df["timestamp"],
            y=df["downtime_risk_pct"],
            mode="lines",
            line={"color": config.STATUS_COLORS["WARNING"], "width": 2},
            hovertemplate="%{x|%H:%M:%S}<br>Risk: %{y:.1f}%<extra></extra>",
        )
    )
    for level_name, threshold in sorted(
        config.PRIORITY_RISK_OVERRIDES.items(), key=lambda kv: kv[1]
    ):
        fig.add_hline(
            y=threshold,
            line={
                "color": config.STATUS_COLORS["CRITICAL"],
                "dash": "dash",
                "width": 1,
            },
            annotation_text=level_name,
            annotation_position="right",
        )
    fig.update_yaxes(range=[0, 100], title_text="Downtime risk (%)")
    fig.update_layout(height=300)
    return _apply_base_layout(fig)




def build_collecting_placeholder() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=_COLLECTING_TEXT,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=240)
    return _apply_base_layout(fig)
