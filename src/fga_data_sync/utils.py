# fga_data_sync/utils.py
from functools import lru_cache
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver
from openfga_sdk.client import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient

from .conf import get_setting
from .exceptions import FGAConfigurationError


@lru_cache(maxsize=1)
def get_fga_client() -> OpenFgaClient:
    """
    Instantiates and caches the OpenFGA client using the packaged `FGA_DATA_SYNC` settings.
    """
    api_url = get_setting("OPENFGA_API_URL")
    store_id = get_setting("OPENFGA_STORE_ID")

    if not store_id:
        raise ImproperlyConfigured(
            "FGA_DATA_SYNC['OPENFGA_STORE_ID'] must be defined in your Django `settings.py`."
        )

    config = ClientConfiguration(api_url=api_url, store_id=store_id)

    try:
        return OpenFgaClient(config)
    except (ValueError, TypeError) as e:
        # Replaced generic Exception with expected initialization errors
        raise FGAConfigurationError(f"Failed to initialize FGA client: {e}") from e


@receiver(setting_changed)
def _clear_fga_client_cache(sender: Any, setting: str, **kwargs: Any) -> None:  # pragma: no cover
    """
    Automatically clears the lru_cache when Django settings are overridden in tests.
    """
    if setting == "FGA_DATA_SYNC":
        get_fga_client.cache_clear()
