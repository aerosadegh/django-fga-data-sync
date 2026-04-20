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
    # Local Dev Settings - Remove it for Production!
    "LOCAL_DEV_FALLBACK": {
        # If True, falls back to Django's native session/token user if Traefik is missing
        "USE_DJANGO_USER": True,
        # Optional: A hardcoded string fallback if you don't want to use the database at all
        "STATIC_USER_ID": None,
    },
}
"""Sensible defaults for the Django FGA Data Sync integration.

Attributes:
    OPENFGA_API_URL (str): The endpoint for the OpenFGA server.
        Defaults to `http://localhost:8080`.
    OPENFGA_STORE_ID (Optional[str]): The specific OpenFGA Store ID.
    BATCH_SIZE (int): Number of items to process in a single synchronization batch.
         Defaults to `50`.
    MAX_RETRIES (int): How many times to retry failed synchronization attempts.
         Defaults to `5`.
    REQUEST_HEADER_MAPPINGS (Dict[str, str]): Mapping of incoming request
        headers to FGA context variables.
    ENABLE_OUTBOX_ADMIN (bool): If True, registers the FGA Outbox model in
        the Django Admin. Defaults to `True`.
    FGA_USER_ATTR (str): The attribute on the request/user object to use
        for FGA identity.
    FGA_USER_PREFIX (str): Prefix added to user IDs (e.g., `user:123`).
    LOCAL_DEV_FALLBACK (Dict[str, Any]): Settings for local development
        when identity providers are absent.

        - **USE_DJANGO_USER**: Fallback to native Django session user.
             Defaults to `True`.
        - **STATIC_USER_ID**: A hardcoded ID for rapid testing.
             Defaults to `None`.
"""


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
