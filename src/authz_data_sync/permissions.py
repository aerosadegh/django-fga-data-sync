import logging
from typing import Protocol

from django.core.exceptions import ImproperlyConfigured
from openfga_sdk.client.models import ClientCheckRequest
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from .structs import FGAViewConfig
from .utils import get_fga_client

logger = logging.getLogger(__name__)


class FGAConfiguredView(Protocol):
    """Protocol defining the expected interface for an FGA-protected view."""

    fga_config: FGAViewConfig
    action: str | None = None


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
        return config

    def has_permission(self, request: Request, view: APIView | FGAConfiguredView) -> bool:
        """Validates identity context and handles creation (POST) parent verification.

        Args:
            request: The incoming HTTP request.
            view: The DRF view instance.

        Returns:
            bool: True if the request is allowed to proceed, False otherwise.
        """
        fga_user: str | None = getattr(request, "fga_user", None)
        if not fga_user:
            logger.warning("FGA Authorization denied: No 'fga_user' found on request.")
            return False

        config = self._get_config(view)

        # Handle POST (Creation) Parent Checks
        if request.method == "POST" and config.create_parent_type:
            # Type hint resolution: __post_init__ guarantees these are strings if one exists
            parent_id: str | None = request.data.get(str(config.create_parent_field))

            if not parent_id:
                logger.warning(
                    f"FGA Authorization denied: Missing parent field "
                    f"'{config.create_parent_field}' in payload."
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

        return True

    def has_object_permission(
        self, request: Request, view: APIView | FGAConfiguredView, obj: object
    ) -> bool:
        """Validates fine-grained object access based on HTTP method or ViewSet action.

        Args:
            request: The incoming HTTP request.
            view: The DRF view instance.
            obj: The database object being accessed.

        Returns:
            bool: True if the user holds the required relation on the object, False otherwise.
        """
        config = self._get_config(view)
        relation: str | None = None

        # 1. Resolve relation via Custom ViewSet Action
        view_action: str | None = getattr(view, "action", None)
        if view_action:
            relation = config.action_relations.get(view_action)

        # 2. Resolve relation via Standard HTTP Methods
        if not relation:
            if request.method in permissions.SAFE_METHODS:
                relation = config.read_relation
            elif request.method in ["PUT", "PATCH"]:
                relation = config.update_relation
            elif request.method == "DELETE":
                relation = config.delete_relation

        if relation:
            fga_user: str | None = getattr(request, "fga_user", None)
            if not fga_user:
                return False

            try:
                # Defensive lookup for object identifier
                object_id = getattr(obj, "id", getattr(obj, "pk", None))
                if not object_id:
                    logger.error(f"Authorization target {obj} lacks an 'id' or 'pk' attribute.")
                    return False

                client = get_fga_client()
                response = client.check(
                    ClientCheckRequest(
                        user=fga_user,
                        relation=relation,
                        object=f"{config.object_type}:{object_id}",
                    )
                )
                return bool(response.allowed)
            except (ValueError, AttributeError, ConnectionError, TimeoutError) as e:
                logger.error(f"FGA network or validation error during object check: {e}")
                return False

        return False
