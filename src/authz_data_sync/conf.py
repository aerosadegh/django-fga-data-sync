# authz_data_sync/conf.py
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# 🤠 Sensible defaults so developers don't have to define everything
DEFAULTS = {
    "OPENFGA_API_URL": "http://localhost:8080",
    "OPENFGA_STORE_ID": None,
    "BATCH_SIZE": 50,
    "MAX_RETRIES": 5,
}


def get_setting(name: str):
    """
    Fetches a setting from the AUTHZ_DATA_SYNC dictionary in django.conf.settings.
    Falls back to the DEFAULTS dictionary if not provided.
    """
    user_settings = getattr(settings, "AUTHZ_DATA_SYNC", {})

    if name not in DEFAULTS:
        raise ImproperlyConfigured(f"'{name}' is not a valid AUTHZ_DATA_SYNC setting.")

    return user_settings.get(name, DEFAULTS[name])
