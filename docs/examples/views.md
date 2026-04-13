# Securing API Views

The developer protects the API using the `IsFGAAuthorized` permission class or the `FGAViewMixin`.

You do not have to write custom logic to parse identity headers.
The `TraefikIdentityMiddleware` dynamically extracts your configured gateway headers (e.g., `X-User-Id`) and attaches them to the request automatically.

Below is the complete implementation for a full CRUD lifecycle across our `Organization` -> `Folder` -> `Document` hierarchy.

---

## 1. The Serializers

First, we define our serializers. Because our OpenFGA integration intercepts the `POST` payload to check parent permissions, the parent ID fields (`organization_id`, `folder_id`) must be writable fields. The `creator_id` is always read-only, as our views inject the identity securely from the Traefik middleware.

```python
# serializers.py
from rest_framework import serializers

from .models import Organization, Folder, Document

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'creator_id']
        read_only_fields = ['creator_id']

class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        # organization_id is required from the client payload so the
        # IsFGAAuthorized permission class can verify parent cascading!
        fields = ['id', 'name', 'organization_id', 'creator_id']
        read_only_fields = ['creator_id']

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        # folder_id is required from the client payload!
        fields = ['id', 'title', 'content', 'folder_id', 'creator_id']
        read_only_fields = ['creator_id']
```

---

## Method A: Using DRF Generic Views

If you prefer building explicit, single-purpose endpoints, DRF Generic API Views are the way to go. Here is how you configure the `fga_config` dataclass for Creation (POST) vs. Detail Mutations (GET/PUT/DELETE).

```python
# views.py (Generics Approach)
from rest_framework import generics
from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig

from .models import Organization, Folder, Document
from .serializers import OrganizationSerializer, FolderSerializer, DocumentSerializer

# ==========================================
# 1. ORGANIZATION VIEWS
# ==========================================
class OrganizationCreateAPIView(generics.CreateAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsFGAAuthorized]

    # Top-level entity: No parent check required in this basic setup.
    fga_config = FGAViewConfig(object_type="organization")

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)

class OrganizationDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsFGAAuthorized]

    fga_config = FGAViewConfig(
        object_type="organization",
        read_relation="can_list_org",
        update_relation="can_manage_settings",
        delete_relation="can_manage_settings"
    )

# ==========================================
# 2. FOLDER VIEWS
# ==========================================
class FolderCreateAPIView(generics.CreateAPIView):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]

    # 🛡️ Tell the shield what the rules are for Creation
    fga_config = FGAViewConfig(
        object_type="folder",
        create_parent_type="organization",
        create_parent_field="organization_id",
        create_relation="can_manage_settings"
    )

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)

class FolderDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]

    fga_config = FGAViewConfig(
        object_type="folder",
        read_relation="can_list_folder",
        update_relation="can_edit_folder",
        delete_relation="can_edit_folder"
    )

# ==========================================
# 3. DOCUMENT VIEWS
# ==========================================
class DocumentCreateAPIView(generics.CreateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]

    # 🛡️ Tell the shield what the rules are for Creation
    fga_config = FGAViewConfig(
        object_type="document",
        create_parent_type="folder",
        create_parent_field="folder_id",
        create_relation="can_add_items"
    )

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)

class DocumentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]

    fga_config = FGAViewConfig(
        object_type="document",
        read_relation="can_read_document",
        update_relation="can_update",
        delete_relation="can_delete"
    )
```

---

## Method B: Using DRF ViewSets (Recommended)

If you prefer building RESTful APIs rapidly with ViewSets and Routers, you can combine all permissions into a single, elegant `FGAViewConfig` class for each model. The `IsFGAAuthorized` permission shield intelligently reads the incoming HTTP method and applies the correct check automatically.

```python
# views.py (ViewSet Approach)
from rest_framework import viewsets
from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig
from .models import Organization, Folder, Document
from .serializers import OrganizationSerializer, FolderSerializer, DocumentSerializer

class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsFGAAuthorized]

    fga_config = FGAViewConfig(
        object_type="organization",
        read_relation="can_list_org",
        update_relation="can_manage_settings",
        delete_relation="can_manage_settings"
    )

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]

    # 🛡️ Handles Object-Level AND Parent Cascading
    fga_config = FGAViewConfig(
        object_type="folder",
        read_relation="can_list_folder",
        update_relation="can_edit_folder",
        delete_relation="can_edit_folder",
        create_parent_type="organization",
        create_parent_field="organization_id",
        create_relation="can_manage_settings"
    )

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]

    # 🛡️ Handles Object-Level AND Parent Cascading
    fga_config = FGAViewConfig(
        object_type="document",
        read_relation="can_read_document",
        update_relation="can_update",
        delete_relation="can_delete",
        create_parent_type="folder",
        create_parent_field="folder_id",
        create_relation="can_add_items"
    )

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)
```


!!! info "How the Magic Happens"
    If a user tries to send a `POST /api/documents/` payload with `{"folder_id": "999", "title": "Secret Doc"}`, the `IsFGAAuthorized` permission class will automatically intercept the request. It will query OpenFGA: *"Does `user:123` have the `can_add_items` permission on `folder:999`?"*

    If OpenFGA says **no**, the view instantly returns a `403 Forbidden` without a single line of business logic running in your ViewSet! If OpenFGA says **yes**, the record saves, and your model automatically fires the new role tuples into the Outbox table for Celery to sync. Clean Architecture at its finest!

---

## Method C: The Unified `FGAViewMixin`

While the `IsFGAAuthorized` permission class is fantastic for explicit authorization boundary checks, the `FGAViewMixin` offers a complete, unified approach for views that also need automatic database filtering.

By defining your `FGAViewConfig`, the mixin handles three massive DRF lifecycle hooks automatically: Queryset Filtering for lists, Parent Cascading for creation, and HTTP method mapping for object details.

When you define a custom action, DRF sets `self.action = "archive"`. Then, when you call `self.get_object()`, DRF automatically triggers `self.check_object_permissions()`. Our `FGAViewMixin` intercepts this, looks up the action name in your `action_relations` dictionary, and enforces the `"can_archive"` rule—all before your business logic even runs!

```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from fga_data_sync.mixins import FGAViewMixin
from fga_data_sync.structs import FGAViewConfig

from .models import Document
from .serializers import DocumentSerializer
from .services import DocumentService

class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
    """
    A unified ViewSet secured entirely by the FGAViewMixin.
    No business logic or permission parsing lives in this class!
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer

    # The single source of truth for view-level authorization!
    fga_config = FGAViewConfig(
        object_type="document",
        read_relation="can_read_document",
        update_relation="can_update",
        delete_relation="can_delete",
        create_parent_type="folder",
        create_parent_field="folder_id",
        create_relation="can_add_items",
        action_relations={
            "archive": "can_archive"
        }
    )

    def perform_create(self, serializer):
        # The mixin already verified we have 'can_add_items' on the parent folder!
        # Now we delegate to our Service layer (Layer 2) to handle business logic.
        raw_user_id = self.request.fga_user.replace("user:", "")

        service = DocumentService()
        service.create_document(
            data=serializer.validated_data,
            creator_id=raw_user_id
        )

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """
        Custom endpoint to archive a document.
        Route: POST /documents/{id}/archive/
        """
        # 1. Fetch the object.
        # CRITICAL: This automatically triggers check_object_permissions().
        # The FGAViewMixin will see self.action == "archive", map it to "can_archive",
        # and query OpenFGA. If denied, it raises 403 Forbidden instantly.
        document = self.get_object()

        # 2. Delegate the actual business logic to the Service Layer
        service = DocumentService()
        service.archive_document(document=document)

        # 3. Return standard REST response
        return Response(
            {"status": "Document successfully archived."},
            status=status.HTTP_200_OK
        )
```

!!! note "Architectural Notes"
    1. **`@action(detail=True)`**: It is crucial that `detail=True` is set. This tells DRF that this endpoint operates on a specific instance (which requires an ID in the URL). This is what allows `self.get_object()` to fetch the specific document so the mixin can check its FGA relation.
    2. **Method constraints**: By restricting `methods=['post']`, we ensure that state-changing operations aren't accidentally triggered via `GET` requests, adhering strictly to RESTful best practices.

---

### How the Mixin Hooks Work Under the Hood

The `FGAViewMixin` overrides three core DRF methods to apply your `FGAViewConfig` dataclass safely:

* **Hook 1: Listing (`get_queryset`)**
    If the request is for a list (meaning no lookup kwarg is present), the mixin extracts the `read_relation`. It reaches out to OpenFGA, fetches an array of allowed IDs using the injected `request.fga_user`, and applies an `.id__in` filter to your standard Django queryset.
* **Hook 2: Creation (`check_permissions`)**
    If the request method is `POST`, the mixin extracts the `create_parent` configuration. It intercepts the incoming JSON payload, grabs the UUID from your specified `create_parent_field` (e.g., `folder_id`), and asks OpenFGA if the user holds the required relation on that parent object. If not, it instantly raises a `PermissionDenied` exception.
* **Hook 3: Mutation/Detail (`check_object_permissions`)**
    When a single object is requested (e.g., for an update or delete), the mixin checks the `update_relation` or `delete_relation` against the current `request.method` (or `action_relations` if a custom ViewSet action is used). It performs a precise `ClientCheckRequest` to ensure the user has the mapped permission on that exact object instance.
