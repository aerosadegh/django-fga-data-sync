# authz_data_sync/permissions.py
from openfga_sdk.client.models import ClientCheckRequest
from rest_framework import permissions

from .utils import get_fga_client


class IsFGAAuthorized(permissions.BasePermission):
    """
    Reads the declarative FGA settings from the view and checks OpenFGA automatically.
    """

    def has_permission(self, request, view):
        # 1. Block unauthorized Traefik requests immediately
        if not getattr(request, "fga_user", None):
            return False

        # 2. Handle POST (Creation) Parent Checks
        if request.method == "POST" and hasattr(view, "fga_create_parent_type"):
            parent_id = request.data.get(view.fga_create_parent_field)
            if not parent_id:
                return False

            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=request.fga_user,  # 🤠 Provided by our Middleware!
                    relation=view.fga_create_relation,
                    object=f"{view.fga_create_parent_type}:{parent_id}",
                )
            )
            return response.allowed

        return True  # Pass to object-level permissions for GET/PUT/DELETE

    def has_object_permission(self, request, view, obj):
        relation = None

        # 🤠 NEW: First, check if this is a custom DRF ViewSet action (e.g., 'comment')
        if hasattr(view, "action") and hasattr(view, "fga_action_relations"):
            relation = view.fga_action_relations.get(view.action)

        # Fallback to standard HTTP methods if no custom action matched
        if not relation:
            if request.method in permissions.SAFE_METHODS:
                relation = getattr(view, "fga_read_relation", None)
            elif request.method in ["PUT", "PATCH"]:
                relation = getattr(view, "fga_update_relation", None)
            elif request.method == "DELETE":
                relation = getattr(view, "fga_delete_relation", None)

        # Execute the check if a relation was found
        if relation and hasattr(view, "fga_object_type"):
            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=request.fga_user,  # 🤠 Provided by our Middleware!
                    relation=relation,
                    object=f"{view.fga_object_type}:{obj.id}",
                )
            )
            return response.allowed

        return False
