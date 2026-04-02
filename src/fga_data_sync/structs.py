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
        - object_type must be non-empty (raises ValueError if empty).
        - Cannot define both parents and creators with overlapping relations (raises ValueError).
        - All parent and creator configurations are validated via their own __post_init__.
        - frozen=True prevents accidental mutation after instantiation.

    Common Patterns:
        - Single parent hierarchy: document -> folder -> organization
        - Multiple parents: file belongs to both project AND folder
        - Creator ownership: users can edit/delete only objects they created
        - Combined: creators get special rights within parent context

    Note:
        This configuration is typically used as a class attribute (`fga_config`)
        on Django models that inherit from `FGAModelSyncMixin`.

    Raises:
        ValueError: If object_type is empty, or if duplicate relations are defined
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

    Notes:
        **Validation Rules:**

        - If any `create_*` parameter is set, all three (`create_parent_type`,
        `create_parent_field`, `create_relation`) must be provided.
        - Partial creation configs raise a `ValueError` to prevent misconfiguration.
        - Relations set to `None` disable that specific authorization check. Use this carefully
        and only when certain operations don't require FGA enforcement.

        **Usage with Views:**
        ```python
        class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="can_read_document",
                update_relation="can_update",
                delete_relation="can_delete",
                create_parent_type="folder",
                create_parent_field="folder_id",
                create_relation="can_add_items"
            )
        ```

    Raises:
        ValueError: If `create_parent_type`, `create_parent_field`, and `create_relation` are
                    partially defined (all or none must be provided).
    """

    object_type: str
    read_relation: str | None = None
    update_relation: str | None = None
    delete_relation: str | None = None

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
