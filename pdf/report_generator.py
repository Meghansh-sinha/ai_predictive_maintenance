
from __future__ import annotations

import time as _time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import List, Optional, Tuple

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from models.data_models import AIInsight, HealthResult
from utils.exceptions import ReportGenerationError
from utils.history import HistoryBuffer
from utils.logger import get_logger

_PAGE_SIZES = {"A4": A4}
_TITLE_SIZE = 20
_HEADING_SIZE = 13
_BODY_SIZE = 9.5
_LINE_SPACING = 1.35
_TABLE_FONT_SIZE = 8.5
_AMBER_SUBSCORE = 60.0
_RED_SUBSCORE = 30.0
_TINT_MIX = 0.82
_NO_AI_TEXT = "AI analysis not generated for this report."
_CHART_WIDTH = 440
_CHART_HEIGHT = 170
_CHART_PAD = 35


def _lighten(hex_color: str, mix: float = _TINT_MIX) -> colors.Color:
    base = colors.HexColor(hex_color)
    return colors.Color(
        base.red + (1 - base.red) * mix,
        base.green + (1 - base.green) * mix,
        base.blue + (1 - base.blue) * mix,
    )


def _make_numbered_canvas(footer_left: str):

    class _NumberedCanvas(pdf_canvas.Canvas):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._saved_states: List[dict] = []

        def showPage(self) -> None:
            self._saved_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._saved_states)
            for state in self._saved_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                super().showPage()
            super().save()

        def _draw_footer(self, total: int) -> None:
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#555555"))
            self.drawString(18 * mm, 10 * mm, footer_left)
            self.drawRightString(
                A4[0] - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {total}"
            )

    return _NumberedCanvas


class PDFReportGenerator:

    def __init__(self, config: ModuleType) -> None:
        self._config = config
        self._logger = get_logger(__name__)
        self._styles = self._build_styles()


    def generate(
        self,
        result: HealthResult,
        history: HistoryBuffer,
        ai_insight: Optional[AIInsight],
    ) -> Path:
        started = _time.monotonic()
        reports_dir = Path(self._config.REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)
        local_now = datetime.now().astimezone()
        filename = self._config.PDF_FILENAME_PATTERN.format(
            machine_id=result.machine_id,
            timestamp=local_now.strftime(self._config.PDF_TIMESTAMP_FORMAT),
        )
        final_path = reports_dir / filename
        temp_path = reports_dir / (filename + ".tmp")
        report_id = f"PM-{result.machine_id}-{local_now.strftime(self._config.PDF_TIMESTAMP_FORMAT)}"

        try:
            story = self._build_story(result, history, ai_insight, local_now)
            self._logger.debug("Report flowables: %d.", len(story))
            margin = self._config.PDF_MARGIN_MM * mm
            document = SimpleDocTemplate(
                str(temp_path),
                pagesize=_PAGE_SIZES[self._config.PDF_PAGE_SIZE],
                leftMargin=margin,
                rightMargin=margin,
                topMargin=margin,
                bottomMargin=margin,
                title=self._config.PDF_REPORT_TITLE,
            )
            footer_left = (
                f"{report_id}  ·  {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                f"  ·  {self._config.PDF_FOOTER_TEXT}"
            )
            document.build(
                story, canvasmaker=_make_numbered_canvas(footer_left)
            )
            temp_path.replace(final_path)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            self._logger.error(
                "PDF generation failed for %s.", filename, exc_info=True
            )
            raise ReportGenerationError(
                "The PDF report could not be generated. Please try again; "
                "details have been written to the application log."
            ) from exc

        elapsed_ms = (_time.monotonic() - started) * 1000.0
        self._logger.info(
            "Report written: %s (%d pages, %.0f ms).",
            final_path,
            document.page,
            elapsed_ms,
        )
        return final_path


    def _build_styles(self) -> dict:
        base = getSampleStyleSheet()
        heading_color = colors.HexColor(self._config.PDF_HEADING_COLOR)
        return {
            "title": ParagraphStyle(
                "ReportTitle",
                parent=base["Title"],
                fontSize=_TITLE_SIZE,
                leading=_TITLE_SIZE * _LINE_SPACING,
                textColor=heading_color,
                spaceAfter=4,
            ),
            "heading": ParagraphStyle(
                "ReportHeading",
                parent=base["Heading2"],
                fontSize=_HEADING_SIZE,
                leading=_HEADING_SIZE * _LINE_SPACING,
                textColor=heading_color,
                spaceBefore=10,
                spaceAfter=4,
            ),
            "body": ParagraphStyle(
                "ReportBody",
                parent=base["BodyText"],
                fontSize=_BODY_SIZE,
                leading=_BODY_SIZE * _LINE_SPACING,
            ),
            "small": ParagraphStyle(
                "ReportSmall",
                parent=base["BodyText"],
                fontSize=8,
                leading=8 * _LINE_SPACING,
                textColor=colors.HexColor("#555555"),
            ),
        }


    def _build_story(
        self,
        result: HealthResult,
        history: HistoryBuffer,
        ai_insight: Optional[AIInsight],
        local_now: datetime,
    ) -> List:
        summary = history.summary()
        story: List = []
        story += self._header_block(result, summary, local_now)
        story += self._executive_summary(result, ai_insight)
        story += self._health_overview_table(result)
        story += self._sensor_detail_table(result, history, summary)
        story += self._trend_chart(history)
        story += self._ai_section(ai_insight)
        story += self._alerts_appendix(history)
        return story

    def _header_block(self, result, summary, local_now) -> List:
        chip = Table(
            [[result.machine_status.name]],
            colWidths=[34 * mm],
            style=TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor(
                            self._config.STATUS_COLORS[
                                result.machine_status.name
                            ]
                        ),
                    ),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
        window_text = (
            f"Reporting window: "
            f"{summary.start_time.astimezone():%Y-%m-%d %H:%M:%S} – "
            f"{summary.end_time.astimezone():%H:%M:%S} "
            f"({summary.window_length} ticks)"
        )
        timestamp_text = (
            f"Report generated {local_now:%Y-%m-%d %H:%M:%S %Z} "
            f"({datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC)"
        )
        return [
            Paragraph(self._config.PDF_REPORT_TITLE, self._styles["title"]),
            Paragraph(
                f"{self._config.MACHINE_NAME} · {result.machine_id}",
                self._styles["body"],
            ),
            Paragraph(timestamp_text, self._styles["small"]),
            Paragraph(window_text, self._styles["small"]),
            Spacer(1, 4),
            chip,
            Spacer(1, 6),
        ]

    def _executive_summary(self, result, ai_insight) -> List:
        non_stale = (
            ai_insight is not None
            and abs(ai_insight.source_health_score - result.health_score)
            <= self._config.AI_STALENESS_SCORE_DELTA
        )
        if non_stale:
            text = ai_insight.summary
        else:
            impact = result.production_impact
            text = (
                f"{self._config.MACHINE_NAME} reports a health score of "
                f"{result.health_score:.1f} ({result.machine_status.name}) "
                f"with a {result.trend.value.lower()} trend. Maintenance "
                f"priority is {result.maintenance_priority.name} with an "
                f"estimated downtime risk of {result.downtime_risk_pct:.1f}%. "
                f"The projected production impact is "
                f"{self._config.CURRENCY_SYMBOL}"
                f"{impact.estimated_loss_per_day:,.0f} per day "
                f"({impact.impact_level})."
            )
        return [
            Paragraph("Executive Summary", self._styles["heading"]),
            Paragraph(text, self._styles["body"]),
        ]

    def _health_overview_table(self, result) -> List:
        impact = result.production_impact
        currency = self._config.CURRENCY_SYMBOL
        rows = [
            ["Health Score", f"{result.health_score:.1f}"],
            ["Status", result.machine_status.name],
            ["Confidence", f"{result.confidence_score:.1f}"],
            [
                "Trend",
                f"{result.trend.value} "
                f"({result.trend_slope:+.2f} pts/tick)",
            ],
            ["Maintenance Priority", result.maintenance_priority.name],
            ["Downtime Risk", f"{result.downtime_risk_pct:.1f}%"],
            [
                "Throughput at Risk",
                f"{impact.throughput_at_risk_units_hr:.1f} units/hr",
            ],
            [
                "Estimated Loss/Day",
                f"{currency}{impact.estimated_loss_per_day:,.0f}",
            ],
            ["Impact Level", impact.impact_level],
        ]
        status_tint = _lighten(
            self._config.STATUS_COLORS[result.machine_status.name]
        )
        priority_color = {
            "LOW": "HEALTHY",
            "MEDIUM": "WARNING",
            "HIGH": "WARNING",
            "URGENT": "CRITICAL",
        }[result.maintenance_priority.name]
        priority_tint = _lighten(self._config.STATUS_COLORS[priority_color])
        table = Table(
            rows,
            colWidths=[55 * mm, 60 * mm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                    ("FONTSIZE", (0, 0), (-1, -1), _TABLE_FONT_SIZE),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (1, 1), (1, 1), status_tint),
                    ("BACKGROUND", (1, 4), (1, 4), priority_tint),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            ),
            hAlign="LEFT",
        )
        return [
            Paragraph("Machine Health Overview", self._styles["heading"]),
            table,
        ]

    def _sensor_detail_table(self, result, history, summary) -> List:
        latest_reading = history.latest()[0].reading
        header = [
            "Sensor",
            "Latest",
            "Min",
            "Mean",
            "Max",
            "Nominal band",
            "Sub-score",
            "Contrib. (pts)",
            "Flags",
        ]
        rows: List[List[str]] = [header]
        tints: List[Tuple[int, colors.Color]] = []
        for index, key in enumerate(self._config.SENSOR_KEYS, start=1):
            spec = self._config.SENSORS[key]
            stats = summary.sensor_stats[key]
            flag_count = sum(
                1
                for validated, _ in history.window(len(history))
                if any(f.sensor_key == key for f in validated.validation_flags)
            )
            sub_score = result.sensor_health[key]
            rows.append(
                [
                    f"{spec['display_name']} ({spec['unit']})",
                    f"{getattr(latest_reading, key):.2f}",
                    f"{stats['min']:.2f}",
                    f"{stats['mean']:.2f}",
                    f"{stats['max']:.2f}",
                    f"{spec['nominal_band'][0]:g}–{spec['nominal_band'][1]:g}",
                    f"{sub_score:.1f}",
                    f"{result.sensor_contributions.get(key, 0.0):.1f}",
                    str(flag_count),
                ]
            )
            if sub_score < _RED_SUBSCORE:
                tints.append(
                    (index, _lighten(self._config.STATUS_COLORS["CRITICAL"]))
                )
            elif sub_score < _AMBER_SUBSCORE:
                tints.append(
                    (index, _lighten(self._config.STATUS_COLORS["WARNING"]))
                )
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
            ("FONTSIZE", (0, 0), (-1, -1), _TABLE_FONT_SIZE - 0.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ] + [
            ("BACKGROUND", (0, row), (-1, row), tint) for row, tint in tints
        ]
        return [
            Paragraph("Sensor Detail", self._styles["heading"]),
            Table(rows, style=TableStyle(style), hAlign="LEFT"),
        ]

    def _trend_chart(self, history) -> List:
        scores = [
            entry_result.health_score
            for _, entry_result in history.window(len(history))
        ]
        max_points = self._config.PDF_TREND_MAX_POINTS
        if len(scores) > max_points:
            step_indices = [
                round(i * (len(scores) - 1) / (max_points - 1))
                for i in range(max_points)
            ]
            scores = [scores[i] for i in step_indices]

        drawing = Drawing(_CHART_WIDTH, _CHART_HEIGHT)
        plot = LinePlot()
        plot.x, plot.y = _CHART_PAD, _CHART_PAD - 12
        plot.width = _CHART_WIDTH - _CHART_PAD - 10
        plot.height = _CHART_HEIGHT - _CHART_PAD
        plot.data = [list(enumerate(scores))]
        plot.yValueAxis.valueMin = 0
        plot.yValueAxis.valueMax = 100
        plot.yValueAxis.valueStep = 20
        plot.xValueAxis.visibleTicks = False
        plot.xValueAxis.visibleLabels = False
        plot.lines[0].strokeColor = colors.HexColor(
            self._config.PDF_HEADING_COLOR
        )
        plot.lines[0].strokeWidth = 1.4

        warning = self._config.STATUS_THRESHOLDS["WARNING"]
        healthy = self._config.STATUS_THRESHOLDS["HEALTHY"]
        zones = (
            (0.0, warning, "CRITICAL"),
            (warning, healthy, "WARNING"),
            (healthy, 100.0, "HEALTHY"),
        )
        for lower, upper, status_name in zones:
            drawing.add(
                Rect(
                    plot.x,
                    plot.y + plot.height * lower / 100.0,
                    plot.width,
                    plot.height * (upper - lower) / 100.0,
                    fillColor=_lighten(
                        self._config.STATUS_COLORS[status_name], 0.88
                    ),
                    strokeColor=None,
                )
            )
        drawing.add(plot)
        drawing.add(
            String(
                plot.x + plot.width / 2,
                4,
                "Ticks (reporting window)",
                fontSize=7.5,
                textAnchor="middle",
            )
        )
        drawing.add(
            String(
                8,
                plot.y + plot.height / 2,
                "Health score",
                fontSize=7.5,
                textAnchor="middle",
            )
        )
        return [
            Paragraph("Health Trend", self._styles["heading"]),
            drawing,
        ]

    def _ai_section(self, ai_insight: Optional[AIInsight]) -> List:
        if ai_insight is None:
            return [
                Paragraph("AI Analysis", self._styles["heading"]),
                Paragraph(_NO_AI_TEXT, self._styles["body"]),
            ]
        heading = (
            "Automated Analysis (offline rule-based)"
            if ai_insight.is_fallback
            else f"AI Analysis (Gemini — {ai_insight.model_name})"
        )
        flowables = [
            Paragraph(heading, self._styles["heading"]),
            Paragraph(ai_insight.summary, self._styles["body"]),
            Paragraph("<b>Probable causes</b>", self._styles["body"]),
        ]
        for cause in ai_insight.probable_causes:
            flowables.append(Paragraph(f"• {cause}", self._styles["body"]))
        flowables.append(
            Paragraph("<b>Recommended actions</b>", self._styles["body"])
        )
        for number, action in enumerate(ai_insight.recommended_actions, 1):
            flowables.append(
                Paragraph(f"{number}. {action}", self._styles["body"])
            )
        flowables.append(
            Paragraph(ai_insight.urgency_note, self._styles["body"])
        )
        return flowables

    def _alerts_appendix(self, history) -> List:
        collected: List[Tuple[str, str]] = []
        for _, entry_result in history.window(len(history)):
            for alert in entry_result.alerts:
                collected.append(
                    (
                        f"{entry_result.timestamp.astimezone():%H:%M:%S}",
                        alert,
                    )
                )
        collected = collected[-self._config.PDF_ALERTS_APPENDIX_MAX:]
        if not collected:
            return []
        rows = [["Time", "Alert"]] + [list(item) for item in collected]
        table = Table(
            rows,
            colWidths=[22 * mm, 145 * mm],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                    ("FONTSIZE", (0, 0), (-1, -1), _TABLE_FONT_SIZE - 0.5),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            ),
            hAlign="LEFT",
        )
        return [
            Paragraph("Alerts Appendix", self._styles["heading"]),
            table,
        ]
