# tests/test_permissions.py
import logging
from typing import ClassVar

import pytest
from django.core.exceptions import ImproperlyConfigured
from openfga_sdk.exceptions import ValidationException
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig

from .models import MockFolder
from .views import FinanceDashboardView

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

    def test_stateless_resolution_via_url_kwarg(self, api_rf, mock_fga_client):
        """
        Verifies that `Workspace_kwarg` extracts the object ID directly from
        the DRF router kwargs, completely bypassing the database object's ID.
        """
        view = DummyProtectedView()

        # Override config for stateless URL resolution
        view.fga_config = FGAViewConfig(
            object_type="organization",
            read_relation="can_view",
            lookup_url_kwarg="org_id",
        )

        # Simulating DRF injecting kwargs from the URL (e.g., /api/orgs/<org_id>/)
        view.kwargs = {"org_id": "acme_123"}

        request = api_rf.get("/dummy/")

        # The dynamic user attribute logic
        from fga_data_sync.conf import get_setting

        setattr(request, get_setting("FGA_USER_ATTR"), "user:bob")

        # Prove that the database object is ignored by passing an empty class
        class EmptyObject:
            pass

        perm = IsFGAAuthorized()
        mock_fga_client.check.return_value.allowed = True

        # Execute check
        assert perm.has_object_permission(request, view, EmptyObject()) is True

        # Verify OpenFGA was queried with the URL Kwarg, NOT an object PK
        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.object == "organization:acme_123"

    def test_stateless_resolution_via_http_header(self, api_rf, mock_fga_client):
        """
        Verifies that `lookup_header` extracts the object ID directly from
        the incoming HTTP headers, completely bypassing the database object's ID.
        """
        view = DummyProtectedView()

        # Override config for stateless Header resolution
        view.fga_config = FGAViewConfig(
            object_type="organization",
            read_relation="can_view",
            lookup_header="HTTP_X_CONTEXT_ORG_ID",
        )
        view.kwargs = {}

        # Simulating Traefik/API Gateway injecting a header into the request
        request = api_rf.get("/dummy/", HTTP_X_CONTEXT_ORG_ID="stark_industries")

        # The dynamic user attribute logic
        from fga_data_sync.conf import get_setting

        setattr(request, get_setting("FGA_USER_ATTR"), "user:bob")

        class EmptyObject:
            pass

        perm = IsFGAAuthorized()
        mock_fga_client.check.return_value.allowed = True

        # Execute check
        assert perm.has_object_permission(request, view, EmptyObject()) is True

        # Verify OpenFGA was queried with the Header value, NOT an object PK
        called_request = mock_fga_client.check.call_args[0][0]
        assert called_request.object == "organization:stark_industries"

    def test_guardrail_list_configs_without_mixin_warns(self, api_rf, caplog):
        """
        Verifies a logger warning is emitted if list configurations are used
        on a view that does not inherit from FGAViewMixin.
        """
        view = DummyProtectedView()

        # Deliberately misconfigure the view by adding list_relation
        view.fga_config = FGAViewConfig(
            object_type="folder",
            read_relation="can_read",
            list_relation="can_list_explicit",
        )

        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()

        # Capture standard logger output instead of Python warnings
        with caplog.at_level(logging.WARNING):
            perm._get_config(view)

        # Mathematical Proof: The log was fired, containing the exact DX instructions
        assert "uses 'list_relation' or 'disable_list_filter'" in caplog.text
        assert "does not inherit from 'FGAViewMixin'" in caplog.text
        assert "will safely ignore these settings" in caplog.text

    def test_permission_dsl_mismatch_raises_improperly_configured(self, api_rf, mock_fga_client):
        """Verifies that an OpenFGA ValidationException triggers the DX guardrail in permissions."""

        view = DummyProtectedView()
        request = api_rf.get("/dummy/1/")
        request.fga_user = "user:bob"

        perm = IsFGAAuthorized()

        # 1. Force the OpenFGA SDK to throw the missing relation error
        mock_fga_client.check.side_effect = ValidationException("relation_not_found")

        # 2. Mathematical Proof: The permission caught it and raised the clean Django exception
        with pytest.raises(ImproperlyConfigured, match="FGA DSL Mismatch"):
            perm.has_object_permission(request, view, MockFolder(id=1))

    def test_permission_parent_check_validation_error(self, api_rf, mock_fga_client):
        """Verifies that a missing DSL relation on POST parent check triggers the guardrail."""
        view = DummyProtectedView()
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_777"}, format="json")

        # Wrap the raw WSGIRequest into a DRF Request to enable `.data` parsing
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:bob"

        # Force the SDK to throw the missing relation error
        mock_fga_client.check.side_effect = ValidationException("relation_not_found")

        with pytest.raises(ImproperlyConfigured, match="FGA DSL Mismatch"):
            # Execute the DRF permission check explicitly using the DRF request
            IsFGAAuthorized().has_permission(drf_request, view)

    def test_permission_object_check_validation_error(self, api_rf, mock_fga_client):
        """Verifies that a missing DSL relation on an object check triggers the guardrail."""
        view = DummyProtectedView()

        # We are testing a PUT request, so we MUST assign an update_relation.
        # Otherwise, the permission class assumes it's an explicit opt-out and bypasses FGA!
        view.fga_config = FGAViewConfig(object_type="folder", update_relation="can_update_folder")

        wsgi_request = api_rf.put("/dummy/1/", {"title": "Updated"}, format="json")

        # Wrap the request for DRF
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:bob"

        mock_fga_client.check.side_effect = ValidationException("relation_not_found")

        with pytest.raises(ImproperlyConfigured, match="FGA DSL Mismatch"):
            IsFGAAuthorized().has_object_permission(drf_request, view, MockFolder(id=1))


# Finance App Test


class TestStatelessDashboard:
    def test_dashboard_access_allowed(self, api_rf, mock_fga_client):
        """
        Verifies that an authorized user can access the aggregated dashboard.
        Notice we DO NOT create any Organization objects in the test database!
        """
        view = FinanceDashboardView.as_view()

        # 1. Simulate Traefik routing the request to the dashboard
        # We inject the Organization ID directly into the headers
        request = api_rf.get("/api/dashboard/", HTTP_X_CONTEXT_ORG_ID="acme_corp")

        # Simulate the middleware attaching the user
        from fga_data_sync.conf import get_setting

        setattr(request, get_setting("FGA_USER_ATTR"), "user:alice")

        # 2. Tell the mock OpenFGA server to ALLOW the request
        mock_fga_client.check.return_value.allowed = True

        # 3. Execute the view
        response = view(request)

        # 4. Verify Success
        assert response.status_code == 200
        assert response.data["dashboard_target"] == "acme_corp"

        # 5. Mathematical Proof of Statelessness
        # We verify OpenFGA was queried using the Header value, not a database ID!
        mock_fga_client.check.assert_called_once()
        called_request = mock_fga_client.check.call_args[0][0]

        assert called_request.user == "user:alice"
        assert called_request.relation == "can_view_finance_dashboard"
        assert called_request.object == "organization:acme_corp"

    def test_dashboard_access_denied_for_intruder(self, api_rf, mock_fga_client):
        """
        Verifies that an unauthorized user is blocked from seeing the dashboard metrics.
        """
        view = FinanceDashboardView.as_view()

        # Intruder tries to look at Stark Industries' dashboard
        request = api_rf.get("/api/dashboard/", HTTP_X_CONTEXT_ORG_ID="stark_industries")

        from fga_data_sync.conf import get_setting

        setattr(request, get_setting("FGA_USER_ATTR"), "user:hacker_bob")

        # 2. Tell the mock OpenFGA server to DENY the request
        mock_fga_client.check.return_value.allowed = False

        # 3. Execute the view and expect a 403 Forbidden
        response = view(request)

        assert response.status_code == 403
