# authz_data_sync/structs.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FGAParentConfig:
    """
    Defines how a child object relates to its parent in the OpenFGA graph.
    """

    relation: str
    parent_type: str
    local_field: str


@dataclass(frozen=True)
class FGACreatorConfig:
    """
    Defines the role assigned to the user who creates an object.
    """

    relation: str
    local_field: str


@dataclass(frozen=True)
class FGAModelConfig:
    """
    Strict configuration object replacing the FGA_SETTINGS dictionary on Models.
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
    """
    Strict configuration object replacing the scattered fga_* attributes on Views.
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
