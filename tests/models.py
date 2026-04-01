# tests/models.py
from django.db import models

from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGACreatorConfig, FGAModelConfig, FGAParentConfig


class MockOrganization(FGAModelSyncMixin, models.Model):
    name = models.CharField(max_length=50)
    creator_id = models.CharField(max_length=50)

    fga_config = FGAModelConfig(
        object_type="organization",
        creators=[FGACreatorConfig(relation="admin", local_field="creator_id")],
    )

    class Meta:
        # 🛠️ Explicitly attach this test model to our package's app registry
        app_label = "fga_data_sync"


class MockFolder(FGAModelSyncMixin, models.Model):
    name = models.CharField(max_length=50)
    org_id = models.CharField(max_length=50)
    creator_id = models.CharField(max_length=50)

    fga_config = FGAModelConfig(
        object_type="folder",
        parents=[
            FGAParentConfig(
                relation="organization",
                parent_type="organization",
                local_field="org_id",
            )
        ],
        creators=[FGACreatorConfig(relation="owner", local_field="creator_id")],
    )

    class Meta:
        # 🛠️ Explicitly attach this test model to our package's app registry
        app_label = "fga_data_sync"
