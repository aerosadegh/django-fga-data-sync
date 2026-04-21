# fga_data_sync/loggers.py
import logging

from django.core.management.color import color_style


class FGAConsoleLogger:
    """
    Centralized console logger for the framework.
    Ensures all framework warnings and errors share a consistent,
    colorized format in the Django development terminal.
    """

    def __init__(self, logger_name: str) -> None:
        self.logger = logging.getLogger(logger_name)
        self.style = color_style()

    def warning(self, message: str) -> None:
        """Outputs a bright yellow warning."""
        formatted_msg = f"⚠️ FGA WARNING: {message}"
        self.logger.warning(self.style.WARNING(formatted_msg))

    def error(self, message: str) -> None:
        """Outputs a bold red error."""
        formatted_msg = f"❌ FGA ERROR: {message}"
        self.logger.error(self.style.ERROR(formatted_msg))

    def info(self, message: str) -> None:
        """Outputs a green informational message."""
        formatted_msg = f"💡 FGA INFO: {message}"
        self.logger.info(self.style.SUCCESS(formatted_msg))

    def debug(self, message: str) -> None:
        """Outputs standard debug text."""
        self.logger.debug(f"🔍 FGA DEBUG: {message}")
