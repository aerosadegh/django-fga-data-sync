# tests/test_utils.py
import pytest
from django.core.exceptions import ImproperlyConfigured

from fga_data_sync.conf import get_setting

# We need to bypass the conftest.py mock just for this file so we can test the real utility
from fga_data_sync.utils import get_fga_client


class TestConfigurationAndUtils:
    def test_get_setting_fallback(self):
        """Verifies that missing settings fall back to DEFAULTS."""
        # BATCH_SIZE is not defined in our test_settings.py, so it should fall back to 50
        assert get_setting("BATCH_SIZE") == 50

    def test_get_invalid_setting_raises_error(self):
        """Verifies that asking for a non-existent setting crashes safely."""
        with pytest.raises(ImproperlyConfigured):
            get_setting("SOME_FAKE_SETTING")

    def test_missing_store_id_raises_error(self, settings):
        """Verifies the client refuses to instantiate without a Store ID."""
        # Temporarily wipe out the AUTHZ_DATA_SYNC settings for this specific test
        settings.AUTHZ_DATA_SYNC = {}

        # Clear the lru_cache on the function so it executes freshly
        get_fga_client.cache_clear()

        with pytest.raises(ImproperlyConfigured) as exc_info:
            get_fga_client()

        assert "OPENFGA_STORE_ID" in str(exc_info.value)
