# authz_data_sync/permissions.py
from typing import Any

from openfga_sdk.client.models import ClientCheckRequest
from rest_framework import permissions
from rest_framework.request import Request

from .structs import FGAViewConfig
from .utils import get_fga_client


class IsFGAAuthorized(permissions.BasePermission):
    """
    Reads the declarative FGA settings from the view's `fga_config`
    and checks OpenFGA automatically.
    """

    def _get_config(self, view: Any) -> FGAViewConfig:
        """Safely extracts and validates the FGAViewConfig from the view."""
        config = getattr(view, "fga_config", None)
        if not isinstance(config, FGAViewConfig):
            raise ValueError(
                f"View '{view.__class__.__name__}' using IsFGAAuthorized must "
                f"define an `fga_config` attribute of type `FGAViewConfig`."
            )
        return config

    def has_permission(self, request: Request, view: Any) -> bool:
        """Validates identity context and handles creation (POST) parent verification."""
        fga_user = getattr(request, "fga_user", None)
        if not fga_user:
            return False

        config = self._get_config(view)

        # Handle POST (Creation) Parent Checks
        if request.method == "POST" and config.create_parent_type:
            # We know the other parent fields are present due to FGAViewConfig validation
            parent_id = request.data.get(config.create_parent_field)
            if not parent_id:
                return False

            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=fga_user,
                    relation=config.create_relation,
                    object=f"{config.create_parent_type}:{parent_id}",
                )
            )
            return response.allowed

        return True  # Pass to object-level permissions for GET/PUT/DELETE

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        """Validates fine-grained object access based on HTTP method or action."""
        config = self._get_config(view)
        relation: str | None = None

        # 1. Check if this is a custom DRF ViewSet action mapping (O(1) dictionary lookup)
        view_action = getattr(view, "action", None)
        if view_action:
            relation = config.action_relations.get(view_action)

        # 2. Fallback to standard HTTP method routing
        if not relation:
            if request.method in permissions.SAFE_METHODS:
                relation = config.read_relation
            elif request.method in ["PUT", "PATCH"]:
                relation = config.update_relation
            elif request.method == "DELETE":
                relation = config.delete_relation

        # Execute the network check if a valid relation was resolved
        if relation:
            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=request.fga_user,  # Provided by our Middleware!
                    relation=relation,
                    object=f"{config.object_type}:{obj.id}",
                )
            )
            return response.allowed

        return False
