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


# For Finance Tests


class Invoice(models.Model):
    """Mock Invoice model for testing the stateless dashboard."""

    organization_id = models.CharField(max_length=255, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=50, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 🛠️ Explicitly attach this test model to our package's test app registry
        app_label = "fga_data_sync"


class Expense(models.Model):
    """Mock Expense model for testing the stateless dashboard."""

    organization_id = models.CharField(max_length=255, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 🛠️ Explicitly attach this test model to our package's test app registry
        app_label = "fga_data_sync"
