"""User-facing application errors."""


class ComplianceSummarizerError(Exception):
    """Base class for actionable, expected application failures."""


class ConfigurationError(ComplianceSummarizerError):
    """The runtime configuration is invalid."""


class WorkbookValidationError(ComplianceSummarizerError):
    """The workbook cannot support a trustworthy compliance conclusion."""


class ReportError(ComplianceSummarizerError):
    """The report could not be written safely."""
