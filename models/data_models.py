
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Mapping, Optional, Tuple



class SimulationScenario(Enum):

    NORMAL = "NORMAL"
    GRADUAL_DEGRADATION = "GRADUAL_DEGRADATION"
    RAPID_DEGRADATION = "RAPID_DEGRADATION"
    INTERMITTENT_FAULT = "INTERMITTENT_FAULT"


class MachineStatus(IntEnum):

    HEALTHY = 1
    WARNING = 2
    CRITICAL = 3


class TrendDirection(Enum):

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"


class MaintenancePriority(IntEnum):

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class ValidationFlag(Enum):

    MISSING_FIELD = "MISSING_FIELD"
    OUT_OF_PHYSICAL_RANGE = "OUT_OF_PHYSICAL_RANGE"
    SPIKE_DETECTED = "SPIKE_DETECTED"
    STUCK_SIGNAL = "STUCK_SIGNAL"
    TIMESTAMP_OUT_OF_ORDER = "TIMESTAMP_OUT_OF_ORDER"


@dataclass(frozen=True)
class SensorFlag:

    sensor_key: Optional[str]
    flag: ValidationFlag




@dataclass(frozen=True)
class SensorReading:

    machine_id: str
    timestamp: datetime
    temperature_c: float
    vibration_mm_s: float
    pressure_bar: float
    current_a: float
    tick: int


@dataclass(frozen=True)
class ValidatedReading:

    reading: SensorReading
    is_valid: bool
    validation_flags: Tuple[SensorFlag, ...]
    normalized: Mapping[str, float]
    deviation: Mapping[str, float]


@dataclass(frozen=True)
class ProductionImpact:

    throughput_at_risk_units_hr: float
    estimated_loss_per_day: float
    impact_level: str


@dataclass(frozen=True)
class HealthResult:

    machine_id: str
    timestamp: datetime
    health_score: float
    machine_status: MachineStatus
    confidence_score: float
    trend: TrendDirection
    trend_slope: float
    maintenance_priority: MaintenancePriority
    downtime_risk_pct: float
    production_impact: ProductionImpact
    sensor_health: Mapping[str, float]
    sensor_contributions: Mapping[str, float]
    alerts: Tuple[str, ...]
    used_fallback_values: bool


@dataclass(frozen=True)
class AIInsight:

    summary: str
    probable_causes: Tuple[str, ...]
    recommended_actions: Tuple[str, ...]
    urgency_note: str
    model_name: str
    generated_at: datetime
    is_fallback: bool
    source_health_score: float


@dataclass(frozen=True)
class HistorySummary:

    window_length: int
    start_time: datetime
    end_time: datetime
    health_min: float
    health_mean: float
    health_max: float
    health_delta: float
    sensor_stats: Mapping[str, Mapping[str, float]]
    invalid_count: int
    critical_count: int
