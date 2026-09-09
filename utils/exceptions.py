
from __future__ import annotations


class PMDashboardError(Exception):
    pass


class ConfigurationError(PMDashboardError):
    pass


class SensorValidationError(PMDashboardError):
    pass


class AnalysisError(PMDashboardError):
    pass


class AIServiceError(PMDashboardError):
    pass


class ReportGenerationError(PMDashboardError):
    pass
