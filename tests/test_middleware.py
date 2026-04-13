# tests/test_middleware.py
from unittest.mock import MagicMock

from fga_data_sync.middleware import TraefikIdentityMiddleware


class TestTraefikIdentityMiddleware:
    def test_middleware_attaches_fga_user_when_header_present(self):
        """Verifies that the X-User-Id header is correctly mapped to request.fga_user."""
        mock_get_response = MagicMock(return_value="response")
        middleware = TraefikIdentityMiddleware(mock_get_response)

        # Create a dummy request with the Traefik header
        mock_request = MagicMock()
        mock_request.headers = {"X-User-Id": "123-abc"}

        response = middleware(mock_request)

        assert mock_request.fga_user == "user:123-abc"
        assert response == "response"

    def test_middleware_sets_none_when_header_missing(self):
        """Verifies the middleware safely handles missing identities."""
        mock_get_response = MagicMock(return_value="response")
        middleware = TraefikIdentityMiddleware(mock_get_response)

        mock_request = MagicMock()
        mock_request.headers = {}

        middleware(mock_request)

        assert mock_request.fga_user is None
