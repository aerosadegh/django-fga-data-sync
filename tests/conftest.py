# tests/conftest.py
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_fga_client(mocker):
    """
    Globally intercepts and mocks the get_fga_client utility for all tests.
    """
    mock_client = MagicMock()

    # Set safe default return values for the FGA SDK models
    mock_client.check.return_value.allowed = True
    mock_client.list_objects.return_value.objects = []

    # 🛠️ THE FIX: Mock the function in the namespaces where it is actually IMPORTED and USED.
    mocker.patch("fga_data_sync.tasks.get_fga_client", return_value=mock_client)
    mocker.patch("fga_data_sync.permissions.get_fga_client", return_value=mock_client)
    mocker.patch("fga_data_sync.mixins.get_fga_client", return_value=mock_client)

    return mock_client


@pytest.fixture
def api_rf():
    """
    Provides a DRF APIRequestFactory for testing IsFGAAuthorized securely.
    """
    from rest_framework.test import APIRequestFactory

    return APIRequestFactory()
