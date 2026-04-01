# src/authz_data_sync/views.py
from openfga_sdk.client.models import ClientListObjectsRequest
from rest_framework import generics

from .utils import get_fga_client


class FGAAuthorizedListAPIView(generics.ListAPIView):
    """
    Automatically filters a DRF List view based on OpenFGA permissions.
    """

    fga_object_type = None  # e.g., "document"
    fga_list_relation = "can_list"  # The default FGA relation required to view

    def get_authorized_ids(self) -> list[str]:
        """Asks OpenFGA for the list of IDs the user is allowed to access."""
        if not self.fga_object_type:
            raise ValueError("You must define `fga_object_type` on the view.")

        client = get_fga_client()
        response = client.list_objects(
            ClientListObjectsRequest(
                user=self.request.fga_user,  # Injected by our Middleware!
                relation=self.fga_list_relation,
                type=self.fga_object_type,
            )
        )

        # OpenFGA returns strings like ["document:123", "document:456"]
        # We strip the prefix to get pure UUIDs for the Django ORM
        prefix = f"{self.fga_object_type}:"
        return [obj_string.replace(prefix, "") for obj_string in response.objects]

    def get_queryset(self):
        """Intercepts the standard DRF queryset and applies the FGA filter."""
        # 1. Ask OpenFGA for the allowed IDs
        allowed_ids = self.get_authorized_ids()

        # 2. Filter the Django database!
        return super().get_queryset().filter(id__in=allowed_ids)
