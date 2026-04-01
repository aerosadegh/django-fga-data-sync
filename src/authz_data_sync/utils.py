# authz_data_sync/utils.py
from functools import lru_cache

from django.core.exceptions import ImproperlyConfigured
from openfga_sdk.client import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient

from .conf import get_setting
from .exceptions import FGAConfigurationError


# This decorator turns the function into a high-performance Singleton!
@lru_cache(maxsize=1)
def get_fga_client() -> OpenFgaClient:
    """
    Instantiates and caches the OpenFGA client using the packaged `AUTHZ_DATA_SYNC` settings.
    Reuses the HTTP connection pool for maximum performance.
    """
    api_url = get_setting("OPENFGA_API_URL")
    store_id = get_setting("OPENFGA_STORE_ID")

    if not store_id:
        raise ImproperlyConfigured(
            "AUTHZ_DATA_SYNC['OPENFGA_STORE_ID'] must be defined in your Django `settings.py`."
        )

    config = ClientConfiguration(api_url=api_url, store_id=store_id)
    try:
        return OpenFgaClient(config)
    except Exception as e:
        raise FGAConfigurationError(f"Failed to initialize FGA client: {e}") from e
