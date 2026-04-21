# tests/test_core.py
import logging

import pytest

from fga_data_sync.exceptions import FGAConfigurationError
from fga_data_sync.loggers import FGAConsoleLogger
from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.utils import get_fga_client

pytestmark = pytest.mark.django_db


class TestCoreComponents:
    def test_outbox_string_representation(self):
        """Verifies the __str__ method of the Outbox model."""
        task = FGASyncOutbox(
            action=FGASyncOutbox.Action.WRITE,
            relation="viewer",
            object_id="document:1",
            status=FGASyncOutbox.Status.PENDING,
        )
        assert str(task) == "WRT viewer for document:1 (PEND)"

    def test_console_logger_info_and_debug(self, caplog):
        """Verifies the info and debug methods of the DX Logger."""
        logger = FGAConsoleLogger("test_logger")

        with caplog.at_level(logging.DEBUG):
            logger.info("Information here")
            logger.debug("Debugging here")

        assert "💡 FGA INFO: Information here" in caplog.text
        assert "🔍 FGA DEBUG: Debugging here" in caplog.text

    def test_fga_client_initialization_error(self, settings, mocker):
        """Verifies that SDK instantiation errors are wrapped safely."""
        settings.FGA_DATA_SYNC = {
            "OPENFGA_STORE_ID": "123",
            "OPENFGA_API_URL": "http://localhost:8080",
        }
        get_fga_client.cache_clear()

        # Force the OpenFGA SDK to fail during initialization
        mocker.patch("fga_data_sync.utils.OpenFgaClient", side_effect=ValueError("Bad URL"))

        with pytest.raises(FGAConfigurationError, match="Failed to initialize FGA client: Bad URL"):
            get_fga_client()
