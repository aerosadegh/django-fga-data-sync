import pytest
from rest_framework import generics
from rest_framework.exceptions import APIException
from rest_framework.request import Request

from fga_data_sync.mixins import FGAViewMixin
from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig
from tests.models import MockFolder

pytestmark = pytest.mark.django_db

# ==========================================
# 🛠️ SHARED CONFIGURATION & FIXTURES
# ==========================================

SHARED_FGA_CONFIG = FGAViewConfig(
    object_type="folder",
    read_relation="can_read",
    update_relation="can_edit",
    delete_relation="can_delete",
    create_parent_type="organization",
    create_parent_field="org_id",
    create_relation="can_create_folders",
)


class PermissionShieldedView(generics.GenericAPIView):
    """View utilizing the decoupled Permission Class approach."""

    queryset = MockFolder.objects.all()
    permission_classes = (IsFGAAuthorized,)
    fga_config = SHARED_FGA_CONFIG


class MixinShieldedView(FGAViewMixin, generics.GenericAPIView):
    """View utilizing the unified Mixin approach."""

    queryset = MockFolder.objects.all()
    fga_config = SHARED_FGA_CONFIG


# Tuple containing the uninstantiated view classes for parameterized testing
VIEW_STRATEGIES = [PermissionShieldedView, MixinShieldedView]


# ==========================================
# 🧪 PARITY TEST SUITE
# ==========================================


class TestAuthorizationParity:
    """Verifies behavioral parity between IsFGAAuthorized and FGAViewMixin."""

    def _prepare_drf_request(
        self, view_class: type, wsgi_request
    ) -> tuple[generics.GenericAPIView, Request]:
        """Helper to fully initialize a DRF request with parsers and authenticators."""
        view = view_class()
        view.kwargs = {}  # Mock the kwargs normally injected by the DRF router
        drf_request = view.initialize_request(wsgi_request)
        view.request = drf_request
        return view, drf_request

    @pytest.mark.parametrize("view_class", VIEW_STRATEGIES, ids=["PermissionClass", "Mixin"])
    def test_parity_missing_identity_is_rejected(self, api_rf, view_class):
        """Both strategies MUST safely reject requests missing the `fga_user` context."""
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_123"}, format="json")
        view, drf_request = self._prepare_drf_request(view_class, wsgi_request)

        # We explicitly DO NOT attach drf_request.fga_user here

        # Both implementations should raise an APIException (401 or 403)
        with pytest.raises(APIException):
            view.check_permissions(drf_request)

    @pytest.mark.parametrize("view_class", VIEW_STRATEGIES, ids=["PermissionClass", "Mixin"])
    def test_parity_post_parent_check_allowed(self, api_rf, mock_fga_client, view_class):
        """Both strategies MUST execute a parent check on POST and pass if FGA allows."""
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_123"}, format="json")
        view, drf_request = self._prepare_drf_request(view_class, wsgi_request)
        drf_request.fga_user = "user:bob"

        mock_fga_client.check.return_value.allowed = True

        # Should NOT raise any exceptions
        view.check_permissions(drf_request)

        # Verify exact same network payload was sent
        mock_fga_client.check.assert_called_once()
        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.user == "user:bob"
        assert called_request.relation == "can_create_folders"
        assert called_request.object == "organization:org_123"

    @pytest.mark.parametrize("view_class", VIEW_STRATEGIES, ids=["PermissionClass", "Mixin"])
    def test_parity_post_parent_check_denied(self, api_rf, mock_fga_client, view_class):
        """Both strategies MUST reject the request if FGA blocks parent creation."""
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_123"}, format="json")
        view, drf_request = self._prepare_drf_request(view_class, wsgi_request)
        drf_request.fga_user = "user:mallory"

        mock_fga_client.check.return_value.allowed = False

        with pytest.raises(APIException):
            view.check_permissions(drf_request)

    @pytest.mark.parametrize("view_class", VIEW_STRATEGIES, ids=["PermissionClass", "Mixin"])
    def test_parity_object_update_denied(self, api_rf, mock_fga_client, view_class):
        """Both strategies MUST enforce the update_relation on PUT methods."""
        folder = MockFolder.objects.create(name="Top Secret", org_id="o1", creator_id="u1")

        wsgi_request = api_rf.put(f"/dummy/{folder.id}/", {"name": "Hacked"}, format="json")
        view, drf_request = self._prepare_drf_request(view_class, wsgi_request)
        drf_request.fga_user = "user:mallory"

        mock_fga_client.check.return_value.allowed = False

        with pytest.raises(APIException):
            view.check_object_permissions(drf_request, folder)

        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.relation == "can_edit"

    @pytest.mark.parametrize("view_class", VIEW_STRATEGIES, ids=["PermissionClass", "Mixin"])
    def test_parity_explicit_bypass_none_relation(self, api_rf, mock_fga_client, view_class):
        """Both strategies MUST bypass FGA network checks if the relation is None."""
        folder = MockFolder.objects.create(name="Public", org_id="o1", creator_id="u1")

        wsgi_request = api_rf.get(f"/dummy/{folder.id}/")
        view, drf_request = self._prepare_drf_request(view_class, wsgi_request)
        drf_request.fga_user = "user:bob"

        # Mutate the configuration at the instance level to explicitly bypass read checks
        view.fga_config = FGAViewConfig(
            object_type="folder",
            read_relation=None,  # Explicit Opt-Out
        )

        # Execute check
        view.check_object_permissions(drf_request, folder)

        # Mathematical proof of parity: The FGA client MUST NOT have been called
        mock_fga_client.check.assert_not_called()
