# authz_data_sync/utils.py
from django.core.exceptions import ImproperlyConfigured
from openfga_sdk.client import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient

from .conf import get_setting


def get_fga_client() -> OpenFgaClient:
    """
    Instantiates the OpenFGA client using the packaged AUTHZ_DATA_SYNC settings.
    """
    api_url = get_setting("OPENFGA_API_URL")
    store_id = get_setting("OPENFGA_STORE_ID")

    if not store_id:
        raise ImproperlyConfigured(
            "AUTHZ_DATA_SYNC['OPENFGA_STORE_ID'] must be defined in your Django settings.py."
        )

    config = ClientConfiguration(api_url=api_url, store_id=store_id)
    return OpenFgaClient(config)
