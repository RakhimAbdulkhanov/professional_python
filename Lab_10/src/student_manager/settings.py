"""Settings module for production configuration."""

from student_manager.config import Settings, get_settings


class SettingsError(ValueError):
    """Configuration error for settings."""


__all__ = ["Settings", "SettingsError", "get_settings"]
