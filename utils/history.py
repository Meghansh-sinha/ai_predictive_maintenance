
from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

import pandas as pd

import config
from models.data_models import HealthResult, HistorySummary, MachineStatus, ValidatedReading

HistoryEntry = Tuple[ValidatedReading, HealthResult]


class HistoryBuffer:

    def __init__(self, max_len: int) -> None:
        self._entries: Deque[HistoryEntry] = deque(maxlen=max_len)

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, validated: ValidatedReading, result: HealthResult) -> None:
        self._entries.append((validated, result))

    def latest(self) -> Optional[HistoryEntry]:
        return self._entries[-1] if self._entries else None

    def window(self, n: int) -> List[HistoryEntry]:
        if n <= 0:
            return []
        entries = list(self._entries)
        return entries[-n:]

    def to_dataframe(self) -> pd.DataFrame:
        flag_columns = [f"{key}_flagged" for key in config.SENSOR_KEYS]
        columns = (
            ["timestamp", "tick", *config.SENSOR_KEYS, "is_valid", *flag_columns]
            + [
                "health_score",
                "machine_status",
                "confidence_score",
                "trend",
                "downtime_risk_pct",
                "maintenance_priority",
            ]
        )

        rows = []
        for validated, result in self._entries:
            reading = validated.reading
            flagged = {
                f"{key}_flagged": any(
                    flag.sensor_key == key for flag in validated.validation_flags
                )
                for key in config.SENSOR_KEYS
            }
            rows.append(
                {
                    "timestamp": reading.timestamp,
                    "tick": reading.tick,
                    **{key: getattr(reading, key) for key in config.SENSOR_KEYS},
                    "is_valid": validated.is_valid,
                    **flagged,
                    "health_score": result.health_score,
                    "machine_status": result.machine_status.name,
                    "confidence_score": result.confidence_score,
                    "trend": result.trend.value,
                    "downtime_risk_pct": result.downtime_risk_pct,
                    "maintenance_priority": result.maintenance_priority.name,
                }
            )

        if not rows:
            frame = pd.DataFrame(columns=columns)
            return frame.astype(
                {
                    "timestamp": "datetime64[ns, UTC]",
                    "tick": "int64",
                    **{key: "float64" for key in config.SENSOR_KEYS},
                    "is_valid": "bool",
                    **{col: "bool" for col in flag_columns},
                    "health_score": "float64",
                    "machine_status": "object",
                    "confidence_score": "float64",
                    "trend": "object",
                    "downtime_risk_pct": "float64",
                    "maintenance_priority": "object",
                }
            )

        frame = pd.DataFrame(rows, columns=columns)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).astype(
            "datetime64[ns, UTC]"
        )
        return frame

    def summary(self) -> HistorySummary:
        if not self._entries:
            raise ValueError(
                "HistoryBuffer.summary() requires at least one entry; "
                "the buffer is empty (cold start, §8.4)."
            )

        readings = [validated.reading for validated, _ in self._entries]
        results = [result for _, result in self._entries]
        scores = [result.health_score for result in results]

        sensor_stats = {
            key: {
                "min": min(getattr(r, key) for r in readings),
                "mean": sum(getattr(r, key) for r in readings) / len(readings),
                "max": max(getattr(r, key) for r in readings),
            }
            for key in config.SENSOR_KEYS
        }

        return HistorySummary(
            window_length=len(self._entries),
            start_time=readings[0].timestamp,
            end_time=readings[-1].timestamp,
            health_min=min(scores),
            health_mean=sum(scores) / len(scores),
            health_max=max(scores),
            health_delta=scores[-1] - scores[0],
            sensor_stats=sensor_stats,
            invalid_count=sum(
                1 for validated, _ in self._entries if not validated.is_valid
            ),
            critical_count=sum(
                1
                for result in results
                if result.machine_status is MachineStatus.CRITICAL
            ),
        )
