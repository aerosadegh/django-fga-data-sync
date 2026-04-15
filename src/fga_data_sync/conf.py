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
    # Enables the Django Admin panel for monitoring the FGA Outbox
    "ENABLE_OUTBOX_ADMIN": True,

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


def validate_settings():
    """
    Ensures the FGA configuration is logically consistent.
    Should be called in AppConfig.ready().
    """
    user_attr = get_setting("FGA_USER_ATTR")
    mappings = get_setting("REQUEST_HEADER_MAPPINGS")

    # 🤠 THE HANDSHAKE CHECK
    # Ensure the attribute we use for checks is actually being populated by the middleware
    if user_attr not in mappings.values():
        raise ImproperlyConfigured(
            f"FGA_DATA_SYNC['FGA_USER_ATTR'] is set to '{user_attr}', "
            f"but this attribute is not defined as a target in 'REQUEST_HEADER_MAPPINGS'. "
            f"The TraefikIdentityMiddleware will never be able to set the user context."
        )

    # Ensure the prefix is provided for Zanzibar compatibility
    prefix = get_setting("FGA_USER_PREFIX")
    if not prefix or not prefix.endswith(":"):
        import warnings

        warnings.warn(
            f"FGA_USER_PREFIX ('{prefix}') does not end with a colon. "
            f"Standard OpenFGA object strings usually follow 'type:id' format.",
            UserWarning,
            stacklevel=2,
        )
