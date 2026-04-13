import logging
from typing import Any, Protocol

from django.core.exceptions import ImproperlyConfigured
from openfga_sdk.client.models import ClientCheckRequest
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from .conf import get_setting
from .structs import FGAViewConfig
from .utils import get_fga_client

logger = logging.getLogger(__name__)


class FGAConfiguredView(Protocol):
    """Protocol defining the expected interface for an FGA-protected view."""

    fga_config: FGAViewConfig
    action: str | None = None
    kwargs: dict[str, Any]


UPDATE_METHODS: set[str] = {"PUT", "PATCH"}
DELETE_METHOD: str = "DELETE"


class IsFGAAuthorized(permissions.BasePermission):
    """Evaluates OpenFGA authorization rules strictly based on the view's FGAViewConfig."""

    def _get_config(self, view: APIView | FGAConfiguredView) -> FGAViewConfig:
        """Safely extracts and validates the FGAViewConfig from the view.

        Args:
            view: The DRF view instance being accessed.

        Returns:
            FGAViewConfig: The validated configuration object.

        Raises:
            ImproperlyConfigured: If the view lacks a valid fga_config.
        """
        config = getattr(view, "fga_config", None)
        if not isinstance(config, FGAViewConfig):
            raise ImproperlyConfigured(
                f"View '{view.__class__.__name__}' using IsFGAAuthorized must "
                f"define an `fga_config` attribute of type `FGAViewConfig`."
            )

        if config.action_relations and not isinstance(view, ViewSetMixin):
            raise ImproperlyConfigured(
                f"View '{view.__class__.__name__}' defines 'action_relations' in its "
                f"FGAViewConfig, but it is not a ViewSet. Standard Generic Views do not support "
                f"@action decorators. Either convert this view to a ViewSet, or remove "
                f"'action_relations' from the config."
            )
        return config

    def has_permission(self, request: Request, view: APIView | FGAConfiguredView) -> bool:
        """Validates identity context and handles creation (POST) parent verification.

        Args:
            request: The incoming HTTP request.
            view: The DRF view instance.

        Returns:
            bool: True if the request is allowed to proceed, False otherwise.
        """
        user_attr = get_setting("FGA_USER_ATTR")
        fga_user: str | None = getattr(request, user_attr, None)

        if not fga_user:
            logger.warning(f"FGA Authorization denied: No '{user_attr}' found on request.")
            return False

        config = self._get_config(view)

        # Handle POST (Creation) Parent Checks
        if request.method == "POST" and config.create_parent_type:
            # Type hint resolution: __post_init__ guarantees these are strings if one exists
            parent_field = str(config.create_parent_field)
            parent_id: str | None = request.data.get(parent_field)

            if not parent_id:
                logger.warning(
                    f"FGA Authorization denied: Missing parent field '{parent_field}' in payload."
                )
                return False

            try:
                client = get_fga_client()
                response = client.check(
                    ClientCheckRequest(
                        user=fga_user,
                        relation=str(config.create_relation),
                        object=f"{config.create_parent_type}:{parent_id}",
                    )
                )
                return bool(response.allowed)
            except (ValueError, ConnectionError, TimeoutError) as e:
                logger.error(f"FGA network or validation error during parent check: {e}")
                return False

        if config.lookup_header or config.lookup_url_kwarg:
            return self.has_object_permission(request, view, obj=None)

        return True

    def has_object_permission(
        self, request: Request, view: APIView | FGAConfiguredView, obj: object
    ) -> bool:
        """Validates fine-grained object access based on HTTP method or ViewSet action.

        If the corresponding relation in the view's FGAViewConfig is explicitly set
        to None, this check is bypassed and access is automatically granted, adhering
        to the documented opt-out contract.

        Args:
            request: The incoming HTTP request.
            view: The DRF view instance.
            obj: The database object being accessed.

        Returns:
            bool: True if the user holds the required relation on the object (or if the
                  check is explicitly disabled), False otherwise.
        """
        config = self._get_config(view)
        required_relation: str | None = None
        is_relation_mapped: bool = False

        # 1. Resolve relation via Custom ViewSet Action
        view_action: str | None = getattr(view, "action", None)
        if view_action and view_action in config.action_relations:
            required_relation = config.action_relations.get(view_action)
            is_relation_mapped = True

        # 2. Resolve relation via Standard HTTP Methods
        if not is_relation_mapped:
            if request.method in permissions.SAFE_METHODS:
                required_relation = config.read_relation
                is_relation_mapped = True
            elif request.method in UPDATE_METHODS:
                required_relation = config.update_relation
                is_relation_mapped = True
            elif request.method == DELETE_METHOD:
                required_relation = config.delete_relation
                is_relation_mapped = True

        # If the HTTP method wasn't mapped at all (e.g., TRACE, CONNECT), deny by default.
        if not is_relation_mapped:
            logger.warning(f"FGA Authorization denied: Unmapped HTTP method '{request.method}'.")
            return False

        # 3. Handle Explicit Opt-Out (Relation is mapped, but explicitly set to None)
        if required_relation is None:
            return True

        # 4. Perform FGA Network Check
        user_attr = get_setting("FGA_USER_ATTR")
        fga_user: str | None = getattr(request, user_attr, None)
        if not fga_user:
            logger.warning("FGA Authorization denied: No 'fga_user' found on request.")
            return False

        try:
            # Defensive lookup for object identifier
            # 🤠 NEW: Resolve Object ID Statelessly OR Statefuly
            if config.lookup_header:
                object_id = request.META.get(config.lookup_header)
            elif config.lookup_url_kwarg:
                object_id = view.kwargs.get(config.lookup_url_kwarg)
            else:
                object_id = getattr(obj, "id", getattr(obj, "pk", None))

            if not object_id:
                logger.error("Authorization target lacks an identifier.")
                return False

            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=fga_user,
                    relation=required_relation,
                    object=f"{config.object_type}:{object_id}",
                )
            )
            return bool(response.allowed)
        except (ValueError, AttributeError, ConnectionError, TimeoutError) as e:
            logger.error(f"FGA network or validation error during object check: {e}")
            return False
