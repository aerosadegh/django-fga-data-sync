# fga_data_sync/batchers.py
from openfga_sdk.client.models import ClientCheckRequest
from rest_framework import serializers

from .conf import get_setting
from .loggers import FGAConsoleLogger
from .utils import get_fga_client

logger = FGAConsoleLogger(__name__)


class FGABatchListSerializer(serializers.ListSerializer):
    """
    Intercepts list serialization to perform a single OpenFGA BatchCheck.
    Prevents N+1 network requests during collection views.
    """

    def to_representation(self, data):
        request = self.context.get("request")
        if not request:
            return super().to_representation(data)

        # 1. Resolve Identity via package settings
        user_attr = get_setting("FGA_USER_ATTR")
        fga_user = getattr(request, user_attr, None)

        if not fga_user:
            return super().to_representation(data)

        iterable = data.all() if hasattr(data, "all") else list(data)
        if not iterable:
            return super().to_representation(data)

        # 2. Extract configuration from child's Meta class
        fga_object_type = getattr(self.child.Meta, "fga_object_type", None)
        fga_permissions = getattr(self.child.Meta, "fga_permissions", [])

        if not fga_object_type or not fga_permissions:
            return super().to_representation(data)

        # 3. Build the SDK Batch Checks
        checks = []
        for obj in iterable:
            # Use .pk to support both integer and UUID primary keys
            object_key = f"{fga_object_type}:{obj.pk}"
            for perm in fga_permissions:
                checks.append(
                    ClientCheckRequest(
                        user=fga_user,
                        relation=perm,
                        object=object_key,
                    )
                )

        # 4. Execute via the cached package client
        fga_client = get_fga_client()
        fga_permissions_map = {}

        try:
            batch_response = fga_client.batch_check(checks)

            # Map the SDK responses into a fast dictionary lookup
            for resp in batch_response.responses:
                # Use getattr to safely read from the SDK response object
                req = getattr(resp, "_request", getattr(resp, "request", None))
                if not req:
                    continue

                obj_key = req.object
                rel = req.relation

                if obj_key not in fga_permissions_map:
                    fga_permissions_map[obj_key] = {}
                fga_permissions_map[obj_key][rel] = resp.allowed

            self.context["fga_permissions_map"] = fga_permissions_map

        except Exception as e:
            logger.error(f"Serializer Batch Check Failed: {e}")
            self.context["fga_permissions_map"] = {}

        return super().to_representation(data)
