# tests/test_views_and_mixins.py
import pytest
from rest_framework import generics
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from fga_data_sync.mixins import FGAViewMixin
from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.structs import FGAViewConfig
from tests.models import MockFolder

pytestmark = pytest.mark.django_db


# ==========================================
# TEST FIXTURE VIEWS
# ==========================================
class DummyListAPIView(FGAViewMixin, generics.ListAPIView):
    """A concrete implementation of the FGAViewMixin and ListAPIView for testing."""

    queryset = MockFolder.objects.all()
    fga_config = FGAViewConfig(
        object_type="folder",
        read_relation="can_list",
    )


class DummyFGAViewMixin(FGAViewMixin, generics.RetrieveUpdateDestroyAPIView):
    """A concrete implementation of the FGAViewMixin for testing."""

    queryset = MockFolder.objects.all()
    lookup_field = "pk"

    # THE FIX: Upgraded to the strict dataclass
    fga_config = FGAViewConfig(
        object_type="folder",
        read_relation="can_list",
        update_relation="can_update",
        delete_relation="can_delete",
        create_parent_type="organization",
        create_parent_field="org_id",
        create_relation="can_add_folder",
    )


# ==========================================
# THE TEST SUITE
# ==========================================
class TestViewsAndMixins:
    # tests/test_views_and_mixins.py

    def test_authorized_list_api_view_filters_queryset(self, api_rf, mock_fga_client):
        """Verifies the standard ListAPIView correctly asks FGA and filters the DB."""
        folder1 = MockFolder.objects.create(name="Public", org_id="o1", creator_id="u1")

        request = api_rf.get("/dummy/")
        request.fga_user = "user:bob"

        view = DummyListAPIView()
        view.request = request
        view.kwargs = {}  # Explicitly initialize kwargs for the test context

        # Mock OpenFGA to ONLY return folder1
        mock_fga_client.list_objects.return_value.objects = [f"folder:{folder1.id}"]

        # Execute the DRF get_queryset method
        qs = view.get_queryset()

        assert qs.count() == 1
        assert qs.first() == folder1

    def test_fgaviewmixin_list_filtering(self, api_rf, mock_fga_client):
        """Verifies the FGAViewMixin Hook 1 (List Filtering)."""
        folder1 = MockFolder.objects.create(name="F1", org_id="o1", creator_id="u1")

        request = api_rf.get("/dummy/")
        request.fga_user = "user:bob"

        view = DummyFGAViewMixin()
        view.request = request
        view.kwargs = {}  # Empty kwargs implies a List route (no PK)

        mock_fga_client.list_objects.return_value.objects = [f"folder:{folder1.id}"]
        qs = view.get_queryset()

        assert qs.count() == 1

    def test_fgaviewmixin_create_parent_check_allowed(self, api_rf, mock_fga_client):
        """Verifies the FGAViewMixin Hook 2 (POST Parent Checking)."""
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_999"}, format="json")

        view = DummyFGAViewMixin()

        # Use the view's native initializer to attach the JSON parsers!
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:bob"
        view.request = drf_request

        # Setup FGA to ALLOW the creation
        mock_fga_client.check.return_value.allowed = True

        # If it passes, it shouldn't raise any exceptions
        view.check_permissions(drf_request)

    def test_fgaviewmixin_create_parent_check_denied(self, api_rf, mock_fga_client):
        """Verifies the FGAViewMixin blocks creation if the user lacks parent roles."""
        wsgi_request = api_rf.post("/dummy/", {"org_id": "org_999"}, format="json")

        view = DummyFGAViewMixin()

        # Use the view's native initializer
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:mallory"
        view.request = drf_request

        # Setup FGA to DENY the creation
        mock_fga_client.check.return_value.allowed = False

        with pytest.raises(PermissionDenied) as exc:
            view.check_permissions(drf_request)

        assert "You must be" in str(exc.value)

    def test_fgaviewmixin_detail_object_check(self, api_rf, mock_fga_client):
        """Verifies the FGAViewMixin Hook 3 (Detail Object Checking)."""
        folder1 = MockFolder.objects.create(name="F1", org_id="o1", creator_id="u1")

        # Test a PUT (Update) request
        request = api_rf.put(f"/dummy/{folder1.id}/", {})
        request.fga_user = "user:bob"

        view = DummyFGAViewMixin()
        view.request = request
        view.kwargs = {"pk": folder1.id}

        mock_fga_client.check.return_value.allowed = True

        view.check_object_permissions(request, folder1)

        # Verify the Mixin asked OpenFGA the correct question based on the 'PUT' method
        mock_fga_client.check.assert_called_once()
        called_request = mock_fga_client.check.call_args[0][0]

        assert called_request.relation == "can_update"  # Mapped from "PUT": "can_update"
        assert called_request.object == f"folder:{folder1.id}"

    def test_fgaviewmixin_missing_fga_user(self, api_rf):
        """Verifies the mixin crashes safely if Traefik user is missing."""
        view = DummyFGAViewMixin()
        view.request = api_rf.get("/dummy/")
        # Intentionally NOT setting view.request.fga_user

        with pytest.raises(AuthenticationFailed) as exc:
            view._get_fga_user()
        assert "Missing identity context" in str(exc.value)

    def test_fgaviewmixin_get_queryset_detail_route(self, api_rf):
        """Verifies get_queryset bypasses FGA checks if it's a detail route (has pk)."""
        view = DummyFGAViewMixin()
        view.request = api_rf.get("/dummy/1/")
        view.request.fga_user = "user:bob"

        # DRF injects kwargs for detail routes (e.g., /dummy/{pk}/)
        view.kwargs = {"pk": "1"}
        qs = view.get_queryset()

        # Compare the compiled SQL strings, because DRF clones the queryset in memory
        assert str(qs.query) == str(view.queryset.all().query)

    def test_fgaviewmixin_get_queryset_missing_config(self, api_rf):
        """Verifies get_queryset bypasses FGA safely if list_relation is missing."""
        view = DummyFGAViewMixin()
        view.request = api_rf.get("/dummy/")
        view.request.fga_user = "user:bob"
        view.kwargs = {}

        # THE FIX: Sabotage the config properly using the dataclass
        view.fga_config = FGAViewConfig(object_type="folder", read_relation=None)

        qs = view.get_queryset()

        assert str(qs.query) == str(view.queryset.all().query)

    def test_fgaviewmixin_check_permissions_missing_payload_field(self, api_rf):
        """Verifies parent checking blocks creation if the payload field is missing."""
        wsgi_request = api_rf.post("/dummy/", {"wrong_key": "123"}, format="json")

        view = DummyFGAViewMixin()
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:bob"
        view.request = drf_request

        with pytest.raises(PermissionDenied) as exc:
            view.check_permissions(drf_request)
        assert "Payload must include parent field" in str(exc.value)

    def test_fgaviewmixin_check_object_permissions_unmapped_method(self, api_rf):
        """Verifies object checks pass through safely if the HTTP method isn't mapped."""
        folder = MockFolder.objects.create(name="F1", org_id="o1", creator_id="u1")

        # Simulate a PATCH request, but we only configured PUT/DELETE/GET in DummyFGAViewMixin
        wsgi_request = api_rf.patch(f"/dummy/{folder.id}/", {"name": "test"}, format="json")

        view = DummyFGAViewMixin()
        drf_request = view.initialize_request(wsgi_request)
        drf_request.fga_user = "user:bob"
        view.request = drf_request

        view.check_object_permissions(drf_request, folder)

    def test_tuple_diffing_on_update(self):
        """Verifies that updating a relationship deletes the old tuple and writes the new one."""
        folder = MockFolder.objects.create(name="Docs", org_id="old_org", creator_id="user_1")

        # Clear the outbox to isolate the update logic
        FGASyncOutbox.objects.all().delete()

        # Mutate the parent organization and save
        folder.org_id = "new_org"
        folder.save()

        # The mixin should have calculated the diff: DELETE old_org, WRITE new_org
        tasks = FGASyncOutbox.objects.all().order_by("created_at")
        assert tasks.count() == 2

        delete_task = tasks.get(action=FGASyncOutbox.Action.DELETE)
        assert delete_task.user_id == "organization:old_org"

        write_task = tasks.get(action=FGASyncOutbox.Action.WRITE)
        assert write_task.user_id == "organization:new_org"

    def test_instance_delete_queues_tuples(self):
        """Verifies the overridden delete() method queues DELETE actions."""
        folder = MockFolder.objects.create(name="Docs", org_id="org1", creator_id="user1")
        FGASyncOutbox.objects.all().delete()

        # Trigger the instance-level delete method
        folder.delete()

        # It should queue 2 DELETE tasks (1 for the parent, 1 for the creator)
        assert FGASyncOutbox.objects.filter(action=FGASyncOutbox.Action.DELETE).count() == 2

    def test_fgaviewmixin_list_relation_override(self, api_rf, mock_fga_client):
        """Verifies list_relation takes precedence over read_relation when filtering lists."""
        view = DummyFGAViewMixin()
        view.request = api_rf.get("/dummy/")
        view.request.fga_user = "user:bob"
        view.kwargs = {}  # Empty kwargs implies a List route

        # 🤠 Override the config to test the separation
        view.fga_config = FGAViewConfig(
            object_type="folder",
            read_relation="can_read_detail",
            list_relation="can_list_specifically",
        )

        mock_fga_client.list_objects.return_value.objects = []
        view.get_queryset()

        # Mathematical Proof: The network check MUST use 'can_list_specifically'
        mock_fga_client.list_objects.assert_called_once()
        called_request = mock_fga_client.list_objects.call_args[0][0]
        assert called_request.relation == "can_list_specifically"

    def test_fgaviewmixin_disable_list_filter(self, api_rf, mock_fga_client):
        """Verifies that disable_list_filter=True entirely bypasses OpenFGA network checks."""
        view = DummyFGAViewMixin()
        view.request = api_rf.get("/dummy/")
        view.request.fga_user = "user:bob"
        view.kwargs = {}

        # 🤠 Override the config to explicitly opt-out of list filtering
        view.fga_config = FGAViewConfig(
            object_type="folder",
            read_relation="can_read_detail",
            disable_list_filter=True,
        )

        qs = view.get_queryset()

        # Mathematical Proof: The network check MUST NOT be called
        mock_fga_client.list_objects.assert_not_called()

        # Mathematical Proof: The queryset MUST NOT be filtered
        assert str(qs.query) == str(view.queryset.all().query)
