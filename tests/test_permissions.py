# tests/test_permissions.py
from typing import ClassVar

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig

from .models import MockFolder

pytestmark = pytest.mark.django_db


# ==========================================
# 🛠️ TEST FIXTURE VIEWS
# ==========================================


class DummyProtectedView(APIView):
    """A standard DRF view protected by our permission class."""

    permission_classes: ClassVar[list] = [IsFGAAuthorized]
    fga_config = FGAViewConfig(
        object_type="folder",
        read_relation="can_read",
        create_parent_type="organization",
        create_parent_field="org_id",
        create_relation="can_add_folder",
    )

    def post(self, request):
        return Response({"status": "created"})

    def get(self, request, pk=None):
        return Response({"status": "ok"})


class DummyProtectedViewSet(ViewSetMixin, APIView):
    """A DRF ViewSet mock to test action_relations safely."""

    permission_classes: ClassVar[list] = [IsFGAAuthorized]


# ==========================================
# 🧪 PERMISSIONS TEST SUITE
# ==========================================


class TestIsFGAAuthorized:
    def test_object_level_permission_checks_http_method(self, api_rf, mock_fga_client):
        """Verifies GET maps to the correct FGA read_relation."""

        class MockObj:
            id = "folder_99"

        mock_obj = MockObj()

        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()
        mock_fga_client.check.return_value.allowed = True
        view_instance = DummyProtectedView()

        result = perm.has_object_permission(request, view_instance, mock_obj)

        assert result is True
        mock_fga_client.check.assert_called_once()
        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.relation == "can_read"
        assert called_request.object == "folder:folder_99"

    def test_missing_fga_user_header_denied(self, api_rf):
        """Fails fast if the Traefik middleware did not attach an identity."""
        view = DummyProtectedView.as_view()
        request = api_rf.get("/dummy/1/")

        # Notice we DO NOT attach request.fga_user here
        response = view(request, pk=1)
        assert response.status_code == 403

    def test_post_creation_parent_check_allowed(self, api_rf, mock_fga_client):
        """Verifies POST requests successfully check the parent's permission."""
        view = DummyProtectedView.as_view()
        request = api_rf.post("/dummy/", {"org_id": "org_777"}, format="json")
        request.fga_user = "user:bob"

        mock_fga_client.check.return_value.allowed = True
        response = view(request)

        assert response.status_code == 200
        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.user == "user:bob"
        assert called_request.relation == "can_add_folder"
        assert called_request.object == "organization:org_777"

    def test_post_creation_parent_check_denied(self, api_rf, mock_fga_client):
        """Verifies POST requests are blocked if FGA returns False."""
        view = DummyProtectedView.as_view()
        request = api_rf.post("/dummy/", {"org_id": "org_777"}, format="json")
        request.fga_user = "user:mallory"

        mock_fga_client.check.return_value.allowed = False
        response = view(request)

        assert response.status_code == 403

    def test_missing_config_raises_error(self, api_rf):
        """Verifies that an improperly configured view crashes loudly."""

        class BadView(APIView):
            permission_classes: ClassVar[list] = [IsFGAAuthorized]

        view = BadView.as_view()
        request = api_rf.get("/dummy/")
        request.fga_user = "user:bob"

        with pytest.raises(ImproperlyConfigured):
            view(request)

    def test_missing_parent_field_denied_safely(self, api_rf):
        """Verifies that forgetting the parent ID in the payload safely blocks access."""
        view = DummyProtectedView.as_view()
        request = api_rf.post("/dummy/", {"wrong_field": "123"}, format="json")
        request.fga_user = "user:bob"

        response = view(request)
        assert response.status_code == 403

    def test_creation_network_failure_fails_safely(self, api_rf, mock_fga_client):
        """Verifies network timeouts during parent checks fail closed (403)."""
        view = DummyProtectedView.as_view()
        request = api_rf.post("/dummy/", {"org_id": "org_777"}, format="json")
        request.fga_user = "user:bob"

        mock_fga_client.check.side_effect = TimeoutError("FGA Server Unreachable")

        response = view(request)
        assert response.status_code == 403

    def test_has_object_permission_no_fga_user(self, api_rf):
        """Verifies object access is denied if Traefik user header is missing."""
        view = DummyProtectedView()
        request = api_rf.get("/dummy/1/")

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, MockFolder(id=1)) is False

    def test_has_object_permission_no_id_on_obj(self, api_rf):
        """Verifies the permission safely rejects objects that lack an ID."""
        view = DummyProtectedView()
        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        class BadObject:
            pass  # No .id or .pk

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, BadObject()) is False

    def test_has_object_permission_network_error(self, api_rf, mock_fga_client):
        """Verifies network timeouts during object checks fail closed (False)."""
        view = DummyProtectedView()
        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        mock_fga_client.check.side_effect = TimeoutError("FGA Down")

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, MockFolder(id=1)) is False

    def test_guardrail_action_relations_on_generic_view(self, api_rf):
        """Verifies that defining action_relations on a non-ViewSet crashes safely."""
        view = DummyProtectedView()
        view.fga_config = FGAViewConfig(
            object_type="folder", action_relations={"custom_action": "can_custom"}
        )
        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()

        with pytest.raises(ImproperlyConfigured) as exc:
            perm._get_config(view)

        assert "is not a ViewSet" in str(exc.value)
        assert "Standard Generic Views do not support @action" in str(exc.value)

    def test_has_object_permission_action_mapping(self, api_rf, mock_fga_client):
        """Verifies custom ViewSet actions map to the correct FGA relation."""
        view = DummyProtectedViewSet()
        view.action = "publish"
        view.fga_config = FGAViewConfig(
            object_type="folder", action_relations={"publish": "publisher"}
        )

        request = api_rf.post("/dummy/1/publish/")
        request.fga_user = "user:bob"
        mock_fga_client.check.return_value.allowed = True

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, MockFolder(id=1)) is True

        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.relation == "publisher"

    def test_has_object_permission_put_maps_to_update_relation(self, api_rf, mock_fga_client):
        """Verifies that PUT requests enforce the 'update_relation'."""
        view = DummyProtectedView()
        view.fga_config = FGAViewConfig(object_type="document", update_relation="editor")

        request = api_rf.put("/dummy/1/", {"title": "Updated"}, format="json")
        request.fga_user = "user:bob"

        mock_fga_client.check.return_value.allowed = True
        perm = IsFGAAuthorized()

        assert perm.has_object_permission(request, view, MockFolder(id=1)) is True

        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.relation == "editor"
        assert called_request.object == "document:1"

    def test_has_object_permission_unmapped_http_method(self, api_rf, mock_fga_client):
        """Verifies that unmapped or rogue HTTP methods (like TRACE) are denied."""
        view = DummyProtectedView()
        view.fga_config = FGAViewConfig(object_type="document", read_relation="reader")

        request = api_rf.generic("TRACE", "/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, MockFolder(id=1)) is False
        mock_fga_client.check.assert_not_called()

    def test_has_object_permission_explicit_opt_out(self, api_rf, mock_fga_client):
        """Verifies that setting a mapped relation to None bypasses the network check."""
        view = DummyProtectedView()
        # Explicitly opt-out of read checks
        view.fga_config = FGAViewConfig(object_type="document", read_relation=None)

        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()
        assert perm.has_object_permission(request, view, MockFolder(id=1)) is True

        # Mathematical proof: It bypassed the check, so the network was never called
        mock_fga_client.check.assert_not_called()
