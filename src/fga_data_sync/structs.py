# fga_data_sync/structs.py
from dataclasses import dataclass, field

__all__ = [
    "FGACreatorConfig",
    "FGAModelConfig",
    "FGAParentConfig",
    "FGAViewConfig",
]


@dataclass(frozen=True)
class FGAParentConfig:
    """Defines how a child object relates to its parent in the OpenFGA authorization graph.

    This configuration establishes a "Structural Link" between objects, enabling
    inherited access patterns. For example, a "folder" belongs to an "organization",
    allowing users with access to the organization to automatically inherit access
    to the folder based on your OpenFGA schema.

    Attributes:
        relation: The structural relationship name in the OpenFGA model (e.g., "organization",
                  "parent"). This must match a relation defined in your FGA schema.
        parent_type: The OpenFGA object type of the parent entity (e.g., "organization",
                     "workspace"). Format should match your FGA type definitions
                     without the colon suffix.
        local_field: The Django model field name that stores the parent's primary key.
                     This field should be a ForeignKey or contain the parent object's ID.

    Example:
        ```python
        FGAParentConfig(
            relation="organization",
            parent_type="organization",
            local_field="org_id"
        )
        ```
        **How it translates to an OpenFGA Tuple:**
        If a `folder` (the model's `object_type`) with ID `123` is saved, and its `org_id`
        is `456`, this configuration automatically generates the following tuple:

        * **User:** `organization:456` *(derived from `parent_type` and `local_field`)*
        * **Relation:** `organization` *(derived from `relation`)*
        * **Object:** `folder:123` *(derived from the model's `object_type` and primary key)*

    Note:
        Multiple parent configurations can be defined for complex hierarchies,
        but each creates separate tuple relationships in OpenFGA.
    """

    relation: str
    parent_type: str
    local_field: str


@dataclass(frozen=True)
class FGACreatorConfig:
    """Defines the ownership role assigned to a user when they create an object.

    This configuration automatically grants the creator specific roles on the
    object they create, implementing the "creator owns their content" pattern. The
    relationship is established at creation time via Django's save lifecycle.

    Attributes:
        relation: The Role name in the OpenFGA model representing ownership
                  (e.g., "owner", "editor", "author"). This must match a role defined
                  in your FGA schema that accepts the `user` type on the left side.
        local_field: The Django model field name that stores the creator's user ID.
                     Typically this is a ForeignKey to the User model or a UUID field
                     named "creator_id", "owner_id", etc.

        user_type: The OpenFGA type for the creator (defaults to "user").
                   Override this if the creator is a machine role, API key, or team (e.g., "team").

    Example:
        ```python
        FGACreatorConfig(
            relation="editor",
            local_field="creator_id"
        )
        ```
        **How it translates to an OpenFGA Tuple:**
        If a `document` (the model's `object_type`) with ID `789` is created by a user with ID
        `abc123`, this configuration automatically generates the following tuple:

        * **User:** `user:abc123` *(derived from `local_field` with an implicit `user:` prefix)*
        * **Relation:** `editor` *(derived from `relation`)*
        * **Object:** `document:789` *(derived from `FGAModelConfig.object_type` and primary key)*

    Common Use Cases:
        - Granting creators implicit edit/delete roles on their objects.
        - Enabling users to list only objects they've created.
        - Implementing audit trails by tracking object ownership.

    Note:
        The creator relationship is typically written to OpenFGA once at object
        creation time and rarely deleted unless explicitly transferring ownership.
    """

    relation: str
    local_field: str
    user_type: str = "user"


@dataclass(frozen=True)
class FGAModelConfig:
    """Complete configuration for synchronizing a Django model with OpenFGA authorization tuples.

    This is the primary configuration class that defines how a Django model maps to OpenFGA
    objects, relationships, and ownership patterns.

    The configuration drives automatic tuple creation/deletion when model instances are
    created, updated, or deleted through the FGAModelSyncMixin.

    Attributes:
        object_type: The OpenFGA type name for this Django model (e.g., "document",
                     "folder"). This should match your FGA schema's type definitions
                     exactly, without the colon suffix. All tuples for this model
                     will use the format "{object_type}:{id}".
        parents: List of parent relationship configurations that establish structural
                 access patterns. Each FGAParentConfig defines how this object relates to
                 parent objects, enabling inherited permissions.
        creators: List of creator relationship configurations that automatically grant
                  ownership roles to users who create instances. Each FGACreatorConfig
                  defines which user field represents the creator and what role name
                  to assign in OpenFGA.

    Example:
        ```python
        FGAModelConfig(
            object_type="document",
            parents=[
                FGAParentConfig(
                    relation="folder",
                    parent_type="folder",
                    local_field="folder_id"
                )
            ],
            creators=[
                FGACreatorConfig(
                    relation="editor",
                    local_field="creator_id"
                )
            ]
        )
        ```

    Validation:
        - `object_type` must be non-empty (raises `ValueError` if empty).
        - Cannot define both parents and creators with overlapping relations (raises `ValueError`).
        - All parent and creator configurations are validated via their own `__post_init__`.
        - `frozen=True` in the `FGAModelConfig` dataclass prevents accidental mutation after
          instantiation.

    Common Patterns:
        - Single parent hierarchy: document -> folder -> organization
        - Multiple parents: file belongs to both project AND folder
        - Creator ownership: users can edit/delete only objects they created
        - Combined: creators get special rights within parent context

    Note:
        This configuration is typically used as a class attribute (`fga_config`)
        on Django models that inherit from `FGAModelSyncMixin`.

    Raises:
        ValueError: If `object_type` is empty, or if duplicate relations are defined
                    across parents and creators (which would cause tuple conflicts).
    """

    object_type: str
    parents: list[FGAParentConfig] = field(default_factory=list)
    creators: list[FGACreatorConfig] = field(default_factory=list)

    def __post_init__(self):
        """Validates configuration state immediately upon instantiation."""
        if not self.object_type:
            raise ValueError("FGAModelConfig must define an 'object_type'.")

        # Collect all relations to check for duplicates
        parent_relations = {p.relation for p in self.parents}
        creator_relations = {c.relation for c in self.creators}

        # Check for overlapping relations between parents and creators
        overlaps = parent_relations & creator_relations
        if overlaps:
            raise ValueError(
                f"FGAModelConfig cannot define the same relation(s) in both "
                f"'parents' and 'creators': {overlaps}. "
                f"This would cause ambiguous tuple generation. "
                f"Models should not assign permissions directly; use either parent "
                f"inheritance OR creator assignment, not both for the same relation."
            )


@dataclass(frozen=True)
class FGAViewConfig:
    """Configuration for enforcing OpenFGA authorization checks on Django views and ViewSets.

    This `dataclass` centralizes all authorization settings needed to protect API endpoints
    with OpenFGA checks. It supports multiple authorization strategies including object-level
    permission checks, filtered list queries, and custom action-based relations.

    Use this configuration with the `IsFGAAuthorized` <u>permission class</u> or
    <u>FGA view mixins</u>
    to automatically enforce access control based on OpenFGA tuples.

    Attributes:
        object_type: The OpenFGA type name for objects managed by this view (e.g., "document",
                     "workspace"). Must match the type used in your FGA schema and model
                     configurations. All authorization checks will target this object type.
        list_relation: The OpenFGA relation required specifically to list objects (GET /api/docs/).
                       If omitted, the framework safely falls back to using `read_relation`.
        disable_list_filter: A strict boolean flag to explicitly bypass FGA
                             filtering on list endpoints.
                             Set to True when you want any authenticated user to see the full list,
                             but still protect the detail/update endpoints. Defaults to False.
        read_relation: The OpenFGA relation required to view/list objects (e.g.,
                       "can_read_document", "can_view"). Users must have this permission on the
                       object to include it in query results or retrieve individual instances.
                       Set to None to skip read authorization checks.
        update_relation: The OpenFGA relation required to modify existing objects (e.g.,
                         "can_update", "can_edit"). Checked on PUT/PATCH requests.
                         Set to None to skip update authorization checks.
        delete_relation: The OpenFGA relation required to remove objects (e.g., "can_delete").
                         Checked on DELETE requests. Set to None to skip
                         delete authorization checks.
        lookup_header: An optional HTTP header name (e.g., "HTTP_X_CONTEXT_ORG_ID")
                       used to extract the target object ID statelessly, bypassing database lookups.
        lookup_url_kwarg: An optional URL kwarg name (e.g., "org_id")
                          used to extract the target object ID from the router statelessly.
        create_parent_type: For POST/creation requests, the OpenFGA type of the parent
                            object that must exist (e.g., "folder", "organization"). Used
                            to verify users have permission to create objects within a
                            specific parent context. Requires create_parent_field and
                            create_relation to also be set.
        create_parent_field: The Django model field containing the parent object's ID.
                             This field is extracted from the request data to build the
                             parent object reference for authorization checks.
        create_relation: The OpenFGA permission required on the parent object to allow
                         creation (e.g., "can_add_items", "can_create_documents").
                         Checked before allowing object creation.
        action_relations: Mapping of custom ViewSet action names to OpenFGA permissions.
                          Use this for non-CRUD actions like "export", "share", "archive".
                          Keys must match the action names in your ViewSet's @action
                          decorators. Values are the required FGA permissions.

    Example:
        **Basic RUD permissions:**
        ```python
        FGAViewConfig(
            object_type="document",
            read_relation="can_read_document",
            update_relation="can_update",
            delete_relation="can_delete"
        )
        ```
        **With creation-time parent check:**
        ```python
        FGAViewConfig(
            object_type="document",
            read_relation="can_read_document",
            # THE "CREATE" PERMISSION:
            create_parent_type="folder",
            create_parent_field="folder_id",
            create_relation="can_add_items"
        )
        ```
        **Complete CRUD permissions:**
        ```python
        FGAViewConfig(
            object_type="document",
            # Read
            read_relation="can_read_document",
            # Update
            update_relation="can_update",
            # Delete
            delete_relation="can_delete",
            # Create
            create_parent_type="folder",
            create_parent_field="folder_id",
            create_relation="can_add_items"
        )
        ```
        **With custom actions:**
        ```python
        FGAViewConfig(
            object_type="document",
            read_relation="can_read_document",
            action_relations={
                "export": "can_export",
                "share": "can_share",
                "archive": "can_archive"
            }
        )
        ```
        ## Read Objects in some patterns:
        **Pattern 1: Secure by Default (Fallback)**

        Both the List and Detail endpoints are protected by the same permission.
        ```python
        FGAViewConfig(
            object_type="document",
            read_relation="can_read_document" # Protects both List and Detail views
        )
        ```

        **Pattern 2: Granular List vs. Detail Control**

        Users need a baseline permission to see the list, but a higher tier to read details.
        ```python
        FGAViewConfig(
            object_type="document",
            list_relation="can_list_documents",       # Protects GET /api/documents/
            read_relation="can_read_document_detail", # Protects GET /api/documents/1/
            update_relation="can_update"
        )
        ```

        **Pattern 3: Explicit Opt-Out (Public List, Protected Detail)**

        Anyone authenticated can view the list, but FGA strictly protects the details.
        ```python
        FGAViewConfig(
            object_type="company",
            disable_list_filter=True,            # Bypasses FGA for GET /api/companies/
            read_relation="can_read_details",    # Protects GET /api/companies/1/
            update_relation="can_update"
        )
        ```

    Notes:
        **Validation Rules:**

        - If any `create_*` parameter is set, all three (`create_parent_type`,
          `create_parent_field`, `create_relation`) must be provided.
        - Partial creation configs raise a `ValueError` to prevent misconfiguration.
        - Relations set to `None` disable that specific authorization check. Use this carefully
          and only when certain operations don't require FGA enforcement.
        - Defining `action_relations` requires the view to inherit from a DRF `ViewSet`. The
          framework will raise an `ImproperlyConfigured` error if used on standard generic views.
        - Ensure that keys defined in `action_relations` map to actual `@action` decorated
          methods physically implemented on your ViewSet.

        **Integration Flexibility:**
        This configuration is structure-agnostic. You can use it alongside either the
        `IsFGAAuthorized` permission class OR the `FGAViewMixin`. Both tools work flawlessly
        across standard Generic Views and complex ViewSets.

        **Minimal Action Example:**
        The keys in `action_relations` must match the method name decorated with `@action`:
        ```python
        from rest_framework import viewsets
        from rest_framework.decorators import action
        from rest_framework.response import Response
        from fga_data_sync.mixins import FGAViewMixin

        class SampleViewSet(FGAViewMixin, viewsets.ModelViewSet):
            # 1. In Config:
            fga_config = FGAViewConfig(
                object_type="document",
                action_relations={"archive": "can_archive"}
            )

            # 2. In ViewSet:
            @action(detail=True, methods=["post"])
            def archive(self, request, pk=None):
                obj = self.get_object()  # Automatically triggers the "can_archive" check!
                return Response({"status": "archived"})
        ```

        **Usage with Generic Views:**
        ```python
        from rest_framework import generics
        from fga_data_sync.permissions import IsFGAAuthorized
        from fga_data_sync.structs import FGAViewConfig

        # 1. Creation View (Handles POST and Parent Cascading)
        class DocumentCreateAPIView(generics.CreateAPIView):
            permission_classes = [IsFGAAuthorized]

            fga_config = FGAViewConfig(
                object_type="document",
                create_parent_type="folder",
                create_parent_field="folder_id",
                create_relation="can_add_items"
            )

        # 2. Detail View (Handles GET, PUT, PATCH, DELETE)
        class DocumentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
            permission_classes = [IsFGAAuthorized]

            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="can_read_document",
                update_relation="can_update",
                delete_relation="can_delete"
            )
        ```

        **Usage with Generic Views and FGAViewMixin:**
        ```python
        from rest_framework import generics
        from fga_data_sync.mixins import FGAViewMixin
        from fga_data_sync.structs import FGAViewConfig

        # 1. Collection View (Handles GET List and POST Create)
        class DocumentListCreateAPIView(FGAViewMixin, generics.ListCreateAPIView):
            queryset = Document.objects.all()
            serializer_class = DocumentSerializer

            # The Mixin uses this config to automatically filter the List (GET)
            # and verify the Parent Role (POST) before creation.
            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="can_read_document",
                create_parent_type="folder",
                create_parent_field="folder_id",
                create_relation="can_add_items"
            )

            def perform_create(self, serializer):
                # The mixin already verified we have 'can_add_items' on the parent folder!
                raw_user_id = self.request.fga_user.replace("user:", "")
                serializer.save(creator_id=raw_user_id)


        # 2. Detail View (Handles GET, PUT, PATCH, DELETE on a specific ID)
        class DocumentDetailAPIView(FGAViewMixin, generics.RetrieveUpdateDestroyAPIView):
            queryset = Document.objects.all()
            serializer_class = DocumentSerializer

            # The Mixin uses this config to automatically verify object-level roles
            # based on the exact HTTP method being used.
            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="can_read_document",
                update_relation="can_update",
                delete_relation="can_delete"
            )
        ```

    Raises:
        ValueError: If `create_parent_type`, `create_parent_field`, and `create_relation` are
                    partially defined (all or none must be provided).
    """

    object_type: str

    list_relation: str | None = None
    disable_list_filter: bool = False  # Explicit opt-out flag

    read_relation: str | None = None
    update_relation: str | None = None
    delete_relation: str | None = None

    # Stateless Resolution
    lookup_header: str | None = None  # e.g., "HTTP_X_CONTEXT_ORG_ID"
    lookup_url_kwarg: str | None = None  # e.g., "org_id"

    # Parent verification for POST/Creation
    create_parent_type: str | None = None
    create_parent_field: str | None = None
    create_relation: str | None = None

    # Custom ViewSet actions mapping
    action_relations: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Fail fast if parent creation settings are partially defined."""
        parent_configs = [
            self.create_parent_type,
            self.create_parent_field,
            self.create_relation,
        ]

        # If any parent config is set, they MUST all be set
        if any(parent_configs) and not all(parent_configs):
            raise ValueError(
                "If defining FGA parent creation rules, 'create_parent_type', "
                "'create_parent_field', and 'create_relation' must all be provided."
            )
