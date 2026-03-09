"""Backward-compatible re-export shim.

SettingsService has been moved to app.services.settings (the package).
This module remains as an import alias so existing code and tests that
reference ``app.services.settings_service.SettingsService`` continue to work
without modification.
"""

from app.services.settings import SettingsService

__all__ = ["SettingsService"]
