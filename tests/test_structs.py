# tests/test_structs.py
import pytest

from fga_data_sync.structs import (
    FGACreatorConfig,
    FGAModelConfig,
    FGAParentConfig,
    FGAViewConfig,
)


class TestFGAStructValidators:
    def test_model_config_empty_object_type(self):
        """Verifies FGAModelConfig rejects an empty object_type."""
        with pytest.raises(ValueError, match="must define an 'object_type'"):
            FGAModelConfig(object_type="")

    def test_model_config_overlapping_relations(self):
        """Verifies FGAModelConfig rejects ambiguous relation setups."""
        with pytest.raises(ValueError, match="cannot define the same relation"):
            FGAModelConfig(
                object_type="document",
                parents=[
                    FGAParentConfig(relation="owner", parent_type="org", local_field="org_id")
                ],
                creators=[FGACreatorConfig(relation="owner", local_field="user_id")],
            )

    def test_view_config_partial_parent_setup(self):
        """Verifies FGAViewConfig forces all or nothing for parent creation logic."""
        with pytest.raises(ValueError, match="must all be provided"):
            # Missing create_parent_field and create_relation
            FGAViewConfig(object_type="document", create_parent_type="folder")
