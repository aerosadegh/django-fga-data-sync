# fga_data_sync/conf.py
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Sensible defaults so developers don't have to define everything
DEFAULTS = {
    "OPENFGA_API_URL": "http://localhost:8080",
    "OPENFGA_STORE_ID": None,
    "BATCH_SIZE": 50,
    "MAX_RETRIES": 5,
    "REQUEST_HEADER_MAPPINGS": {
        "X-User-Id": "fga_user",
        # "X-Context-Org-Id": "fga_tenant",
        # "X-Department-Id": "fga_department",
        # "X-Clearance-Level": "fga_clearance",
    },
    # Tells the Mixins/Permissions which attribute to use for FGA checks
    "FGA_USER_ATTR": "fga_user",
    # Prefix added automatically to the user ID
    "FGA_USER_PREFIX": "user:",
}


def get_setting(name: str):
    """
    Fetches a setting from the `FGA_DATA_SYNC` dictionary in `django.conf.settings`.
    Falls back to the `DEFAULTS` dictionary if not provided.
    """
    user_settings = getattr(settings, "FGA_DATA_SYNC", {})

    if name not in DEFAULTS:
        raise ImproperlyConfigured(f"'{name}' is not a valid FGA_DATA_SYNC setting.")

    return user_settings.get(name, DEFAULTS[name])
