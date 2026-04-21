# tests/test_conf.py
import pytest
from django.core.exceptions import ImproperlyConfigured

from fga_data_sync.conf import validate_settings


class TestSettingsValidation:
    def test_validate_settings_handshake_failure(self, mocker):
        """Verifies that a mismatch between header targets and the user attribute crashes safely."""

        # Mock settings to create a mismatch: mapping targets "fga_tenant", but expecting "fga_user"
        def mock_setting(key):
            if key == "FGA_USER_ATTR":
                return "fga_user"
            elif key == "REQUEST_HEADER_MAPPINGS":
                return {"X-User-Id": "fga_tenant"}
            return "user:"

        mocker.patch("fga_data_sync.conf.get_setting", side_effect=mock_setting)

        with pytest.raises(ImproperlyConfigured, match="never be able to set the user context"):
            validate_settings()

    def test_validate_settings_missing_prefix_colon(self, mocker):
        """Verifies that a missing colon in the prefix throws a UserWarning."""

        def mock_setting(key):
            if key == "FGA_USER_PREFIX":
                return "user"  # Missing the colon!
            elif key == "REQUEST_HEADER_MAPPINGS":
                return {"X-User-Id": "fga_user"}
            return "fga_user"

        mocker.patch("fga_data_sync.conf.get_setting", side_effect=mock_setting)

        with pytest.warns(UserWarning, match="does not end with a colon"):
            validate_settings()
