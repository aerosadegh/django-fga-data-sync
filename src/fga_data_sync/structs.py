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

    This configuration establishes hierarchical relationships between objects, enabling
    inherited access patterns. For example, a "document" may belong to a "workspace",
    and users with access to the workspace automatically gain access to its documents.

    Attributes:
        relation: The relationship name in the OpenFGA model (e.g., "parent", "owner",
                  "belongs_to"). This must match a relation defined in your FGA schema.
        parent_type: The OpenFGA object type of the parent entity (e.g., "workspace",
                     "organization", "project"). Format should match your FGA type
                     definitions without the colon suffix.
        local_field: The Django model field name that stores the parent's primary key.
                     This field should be a ForeignKey or contain the parent object's ID.

    Example:
        >>> FGAParentConfig(
        ...     relation="parent",
        ...     parent_type="workspace",
        ...     local_field="workspace_id"
        ... )
        # This means: document:123 has parent workspace:456

    Note:
        Multiple parent configurations can be defined for complex hierarchies,
        but each creates separate tuple relationships in OpenFGA.
    """

    relation: str
    parent_type: str
    local_field: str


@dataclass(frozen=True)
class FGACreatorConfig:
    """Defines the ownership relationship assigned to a user when they create an object.

    This configuration automatically grants the creator specific permissions on the
    object they create, implementing the "creator owns their content" pattern. The
    relationship is established at creation time via signals or model hooks.

    Attributes:
        relation: The relationship name in the OpenFGA model representing ownership
                  or creation rights (e.g., "creator", "owner", "author"). This must
                  match a relation defined in your FGA schema that accepts the user
                  type on the left side.
        local_field: The Django model field name that stores the creator's user ID.
                     Typically this is a ForeignKey to the User model or a field
                     named "created_by", "owner", etc.

    Example:
        >>> FGACreatorConfig(
        ...     relation="creator",
        ...     local_field="created_by_id"
        ... )
        # This means: user:abc123 is the creator of document:xyz789

    Common Use Cases:
        - Granting creators implicit edit/delete permissions on their objects
        - Enabling users to list only objects they've created
        - Implementing audit trails by tracking object ownership

    Note:
        The creator relationship is typically written to OpenFGA once at object
        creation time and rarely deleted unless transferring ownership.
    """

    relation: str
    local_field: str


@dataclass(frozen=True)
class FGAModelConfig:
    """Complete configuration for synchronizing a Django model with OpenFGA authorization tuples.

    This is the primary configuration class that defines how a Django model maps to OpenFGA
    objects, relationships, and ownership patterns. It replaces the legacy dictionary-based
    FGA_SETTINGS approach with a type-safe, validated dataclass.

    The configuration drives automatic tuple creation/deletion when model instances are
    created, updated, or deleted through Django signals or explicit API calls.

    Attributes:
        object_type: The OpenFGA type name for this Django model (e.g., "document",
                     "workspace", "project"). This should match your FGA schema's type
                     definitions exactly, without the colon suffix. All tuples for this
                     model will use the format "{object_type}:{id}".
        parents: List of parent relationship configurations that establish hierarchical
                 access patterns. Each FGAParentConfig defines how this object relates to
                 parent objects, enabling inherited permissions (e.g., "all documents in
                 workspace X inherit workspace permissions").
        creators: List of creator relationship configurations that automatically grant
                  ownership rights to users who create instances. Each FGACreatorConfig
                  defines which user field represents the creator and what relation name
                  to use in OpenFGA (e.g., "creator", "owner").

    Example:
        >>> FGAModelConfig(
        ...     object_type="document",
        ...     parents=[
        ...         FGAParentConfig(
        ...             relation="parent",
        ...             parent_type="workspace",
        ...             local_field="workspace_id"
        ...         )
        ...     ],
        ...     creators=[
        ...         FGACreatorConfig(
        ...             relation="creator",
        ...             local_field="created_by_id"
        ...         )
        ...     ]
        ... )

    Validation:
        - object_type must be non-empty (raises ValueError if empty)
        - All parent and creator configurations are validated via their own __post_init__
        - frozen=True prevents accidental mutation after instantiation

    Common Patterns:
        - Single parent hierarchy: document -> workspace -> organization
        - Multiple parents: file belongs to both project AND folder
        - Creator ownership: users can edit/delete only objects they created
        - Combined: creators get special rights within parent context

    Note:
        This configuration is typically used in model metadata registries or as a
        class attribute on Django models that need FGA synchronization.
    """

    object_type: str
    parents: list[FGAParentConfig] = field(default_factory=list)
    creators: list[FGACreatorConfig] = field(default_factory=list)

    def __post_init__(self):
        """Validates configuration state immediately upon instantiation."""
        if not self.object_type:
            raise ValueError("FGAModelConfig must define an 'object_type'.")


@dataclass(frozen=True)
class FGAViewConfig:
    """Configuration for enforcing OpenFGA authorization checks on Django views and ViewSets.

    This dataclass centralizes all authorization settings needed to protect API endpoints
    with OpenFGA checks. It supports multiple authorization strategies including object-level
    permission checks, filtered list queries, and custom action-based relations.

    Use this configuration with the IsFGAAuthorized permission class and FGA view mixins
    to automatically enforce access control based on OpenFGA tuples.

    Attributes:
        object_type: The OpenFGA type name for objects managed by this view (e.g., "document",
                     "workspace"). Must match the type used in your FGA schema and model
                     configurations. All authorization checks will target this object type.
        read_relation: The OpenFGA relation required to view/list objects (e.g., "reader",
                       "viewer", "can_view"). Users must have this relation with the object
                       to include it in query results or retrieve individual instances.
                       Set to None to skip read authorization checks.
        update_relation: The OpenFGA relation required to modify existing objects (e.g.,
                         "editor", "writer", "can_edit"). Checked on PUT/PATCH requests.
                         Set to None to skip update authorization checks.
        delete_relation: The OpenFGA relation required to remove objects (e.g., "deleter",
                         "can_delete"). Checked on DELETE requests. Set to None to skip
                         delete authorization checks.
        create_parent_type: For POST/creation requests, the OpenFGA type of the parent
                            object that must exist (e.g., "workspace", "project"). Used
                            to verify users have permission to create objects within a
                            specific parent context. Requires create_parent_field and
                            create_relation to also be set.
        create_parent_field: The Django model field containing the parent object's ID.
                             This field is extracted from the request data to build the
                             parent object reference for authorization checks.
        create_relation: The OpenFGA relation required between the user and the parent
                         object to allow creation (e.g., "can_create_documents",
                         "member"). Checked before allowing object creation.
        action_relations: Mapping of custom ViewSet action names to OpenFGA relations.
                          Use this for non-CRUD actions like "export", "share", "archive".
                          Keys must match the action names in your ViewSet's @action
                          decorators. Values are the required FGA relations.

    Example:
        >>> # Basic CRUD permissions
        >>> FGAViewConfig(
        ...     object_type="document",
        ...     read_relation="reader",
        ...     update_relation="editor",
        ...     delete_relation="deleter"
        ... )
        >>>
        >>> # With creation-time parent check
        >>> FGAViewConfig(
        ...     object_type="document",
        ...     read_relation="reader",
        ...     create_parent_type="workspace",
        ...     create_parent_field="workspace_id",
        ...     create_relation="can_create_documents"
        ... )
        >>>
        >>> # With custom actions
        >>> FGAViewConfig(
        ...     object_type="document",
        ...     read_relation="reader",
        ...     action_relations={
        ...         "export": "can_export",
        ...         "share": "can_share",
        ...         "archive": "can_archive"
        ...     }
        ... )

    Validation:
        - If any create_* parameter is set, all three (create_parent_type,
          create_parent_field, create_relation) must be provided
        - Partial creation configs raise ValueError to prevent misconfiguration

    Usage with Views:
        class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="reader",
                update_relation="editor"
            )

    Note:
        Relations set to None disable that specific authorization check. Use this
        carefully and only when certain operations don't require FGA enforcement.

    Raises:
        ValueError: If create_parent_type, create_parent_field, and create_relation are
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
