# authz_data_sync/apps.py
from django.apps import AppConfig


class AuthzDataSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authz_data_sync"  # Must match the folder name exactly
    verbose_name = "Authorization Data Sync (OpenFGA)"
