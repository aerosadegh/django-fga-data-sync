# fga_data_sync/apps.py
from django.apps import AppConfig


class AuthzDataSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fga_data_sync"  # Must match the folder name exactly
    verbose_name = "Authorization Data Sync (OpenFGA)"

    def ready(self):
        from .conf import validate_settings

        # Run validation as soon as Django starts
        validate_settings()
