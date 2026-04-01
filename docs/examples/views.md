# Securing API Views

The developer protects the API using the `IsFGAAuthorized` permission class we built. 

You do not have to write custom logic to parse identity headers. The `TraefikIdentityMiddleware` automatically extracts `X-User-Id`.

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

If you prefer building explicit, single-purpose endpoints, DRF Generic API Views are the way to go. Here is how you configure the `IsFGAAuthorized` rules for Creation (POST) vs. Detail Mutations (GET/PUT/DELETE).

```python
# views.py (Generics Approach)
from rest_framework import generics
from authz_data_sync.permissions import IsFGAAuthorized

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
    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")         
        serializer.save(creator_id=raw_user_id) 

class OrganizationDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsFGAAuthorized]

    fga_object_type = "organization"
    fga_read_relation = "can_list_org"
    fga_update_relation = "can_manage_settings"
    fga_delete_relation = "can_manage_settings"

# ==========================================
# 2. FOLDER VIEWS
# ==========================================
class FolderCreateAPIView(generics.CreateAPIView):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]     

    # 🛡️ Tell the shield what the rules are for Creation
    fga_create_parent_type = "organization"     
    fga_create_parent_field = "organization_id"  
    fga_create_relation = "can_manage_settings"  

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")         
        serializer.save(creator_id=raw_user_id) 

class FolderDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]

    fga_object_type = "folder"
    fga_read_relation = "can_list_folder"
    fga_update_relation = "can_edit_folder"
    fga_delete_relation = "can_edit_folder"

# ==========================================
# 3. DOCUMENT VIEWS
# ==========================================
class DocumentCreateAPIView(generics.CreateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]     

    # 🛡️ Tell the shield what the rules are for Creation
    fga_create_parent_type = "folder"     
    fga_create_parent_field = "folder_id"    
    fga_create_relation = "can_add_items"      

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")         
        serializer.save(creator_id=raw_user_id) 

class DocumentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]

    fga_object_type = "document"
    fga_read_relation = "can_read_document"
    fga_update_relation = "can_update"
    fga_delete_relation = "can_delete"
```

---

## Method B: Using DRF ViewSets

If you prefer building RESTful APIs rapidly with ViewSets and Routers, you can combine all permissions into a single, elegant class for each model. The `IsFGAAuthorized` permission shield intelligently reads the incoming HTTP method and applies the correct check automatically.

```python
# views.py (ViewSet Approach)
from rest_framework import viewsets
from authz_data_sync.permissions import IsFGAAuthorized
from .models import Organization, Folder, Document
from .serializers import OrganizationSerializer, FolderSerializer, DocumentSerializer

class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsFGAAuthorized]

    # Object-level Permissions (GET, PUT, PATCH, DELETE)
    fga_object_type = "organization"
    fga_read_relation = "can_list_org"
    fga_update_relation = "can_manage_settings"
    fga_delete_relation = "can_manage_settings"

    def perform_create(self, serializer):
        # The Traefik middleware provides request.fga_user (e.g., "user:123")
        # Strip "user:" to store the raw UUID in the database
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = [IsFGAAuthorized]

    # Object-level Permissions (GET, PUT, PATCH, DELETE)
    fga_object_type = "folder"
    fga_read_relation = "can_list_folder"
    fga_update_relation = "can_edit_folder"
    fga_delete_relation = "can_edit_folder"

    # 🛡️ Parent Check for POST (Creation)
    # The user must have 'can_manage_settings' on the parent Organization to create a folder!
    fga_create_parent_type = "organization"
    fga_create_parent_field = "organization_id" 
    fga_create_relation = "can_manage_settings" 

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsFGAAuthorized]

    # Object-level Permissions (GET, PUT, PATCH, DELETE)
    fga_object_type = "document"
    fga_read_relation = "can_read_document"
    fga_update_relation = "can_update"
    fga_delete_relation = "can_delete"

    # 🛡️ Parent Check for POST (Creation)
    # The user must have 'can_add_items' on the parent Folder to create a document!
    fga_create_parent_type = "folder"
    fga_create_parent_field = "folder_id" 
    fga_create_relation = "can_add_items"

    def perform_create(self, serializer):
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)
```


!!! info "How the Magic Happens"
    If a user tries to send a `POST /api/documents/` payload with `{"folder_id": "999", "title": "Secret Doc"}`, the `IsFGAAuthorized` permission class will automatically intercept the request. It will query OpenFGA: *"Does `user:123` have the `can_add_items` permission on `folder:999`?"* 

    If OpenFGA says **no**, the view instantly returns a `403 Forbidden` without a single line of business logic running in your ViewSet! If OpenFGA says **yes**, the record saves, and your model automatically fires the new role tuples into the Outbox table for Celery to sync. Clean Architecture at its finest!


---

## The `FGAViewMixin` & `FGA_VIEW_SETTINGS`

While the `IsFGAAuthorized` permission class is fantastic for explicitly mapping properties on your views, the `FGAViewMixin` offers an alternative, highly condensed dictionary approach. 

The developer defines the `FGA_VIEW_SETTINGS` completely based on their business logic to handle three massive DRF lifecycle hooks automatically: Queryset Filtering for lists, Parent Cascading for creation, and HTTP method mapping for object details.

Here is how you would use it on a unified `ModelViewSet`:

```python
# views.py
from rest_framework import viewsets
from authz_data_sync.mixins import FGAViewMixin

from .models import Document
from .serializers import DocumentSerializer
from .services import DocumentService # Our clean architecture service!

class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
    """
    A unified ViewSet secured entirely by the FGAViewMixin.
    No business logic or permission parsing lives in this class!
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    
    # The single source of truth for view-level authorization!
    FGA_VIEW_SETTINGS = {
        # 1. Base Entity Type
        "object_type": "document",
        
        # 2. LISTING: Relation needed to see the list
        "list_relation": "can_read_document",
        
        # 3. CREATION: Dict defining parent requirements for POST
        "create_parent": {
            "parent_type": "folder",
            "payload_field": "folder_id",
            "relation": "can_add_items"
        },
        
        # 4. MUTATION/DETAIL: Map of HTTP Method -> Relation
        "detail_relations": {
            "GET": "can_read_document",
            "PUT": "can_update",
            "PATCH": "can_update",
            "DELETE": "can_delete"
        }
    }

    def perform_create(self, serializer):
        # The mixin already verified we have 'can_add_items' on the parent folder!
        # Now we delegate to our Service layer (Layer 2) to handle business logic.
        raw_user_id = self.request.fga_user.replace("user:", "")
        
        service = DocumentService()
        service.create_document(
            data=serializer.validated_data, 
            creator_id=raw_user_id
        )
```

### How the Mixin Hooks Work Under the Hood

The `FGAViewMixin` overrides three core DRF methods to apply your `FGA_VIEW_SETTINGS` dictionary safely:

*   **Hook 1: Listing (`get_queryset`)**
    If the request is for a list (meaning no lookup kwarg is present), the mixin extracts the `list_relation`. It reaches out to OpenFGA, fetches an array of allowed IDs using the injected `request.fga_user`, and applies an `.id__in` filter to your standard Django queryset. 
*   **Hook 2: Creation (`check_permissions`)**
    If the request method is `POST`, the mixin extracts the `create_parent` configuration. It intercepts the incoming JSON payload, grabs the UUID from your specified `payload_field` (e.g., `folder_id`), and asks OpenFGA if the user holds the required relation on that parent object. If not, it instantly raises a `PermissionDenied` exception.
*   **Hook 3: Mutation/Detail (`check_object_permissions`)**
    When a single object is requested (e.g., for an update or delete), the mixin checks the `detail_relations` dictionary against the current `request.method`. It performs a precise `ClientCheckRequest` to ensure the user has the mapped permission on that exact object instance.