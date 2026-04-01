# authz_data_sync/mixins.py
import uuid
from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from openfga_sdk.client.models import ClientCheckRequest, ClientListObjectsRequest
from rest_framework.exceptions import PermissionDenied

from .structs import FGAModelConfig
from .utils import get_fga_client


class AuthzSyncMixin:
    """
    Structure-agnostic mixin for synchronizing Django models to OpenFGA via the Outbox pattern.
    Requires `fga_config` to be defined on the model using `FGAModelConfig`.
    """

    # Enforce strict typing on the configuration object
    fga_config: ClassVar[FGAModelConfig | None] = None

    pk: int | str | uuid.UUID | None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._original_tuples = self._generate_authz_tuples() if self.pk else []

    def _generate_authz_tuples(self) -> list[dict[str, str]]:
        """
        Generates standard OpenFGA tuples based on the model's FGA configuration.

        Returns:
            List[Dict[str, str]]: A list of dictionaries representing Zanzibar tuples.

        Raises:
            ImproperlyConfigured: If fga_config is missing or invalid.
        """
        config = getattr(self, "fga_config", None)

        if not isinstance(config, FGAModelConfig):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must define a valid `fga_config` "
                f"of type `FGAModelConfig`."
            )

        object_string = f"{config.object_type}:{self.pk}"
        tuples: list[dict[str, str]] = []

        # Iterate strictly-typed parent configurations
        for parent in config.parents:
            parent_id = getattr(self, parent.local_field, None)
            if parent_id:
                tuples.append(
                    {
                        "user": f"{parent.parent_type}:{parent_id}",
                        "relation": parent.relation,
                        "object": object_string,
                    }
                )

        # Iterate strictly-typed creator configurations
        for creator in config.creators:
            user_id = getattr(self, creator.local_field, None)
            if user_id:
                tuples.append(
                    {
                        "user": f"user:{user_id}",
                        "relation": creator.relation,
                        "object": object_string,
                    }
                )

        return tuples

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        with transaction.atomic():
            super().save(*args, **kwargs)
            current_tuples = self._generate_authz_tuples()

            if is_new:
                for t in current_tuples:
                    self._queue_outbox("WRITE", t)
            else:
                old_set = {
                    f"{t['user']}::{t['relation']}::{t['object']}" for t in self._original_tuples
                }
                new_set = {f"{t['user']}::{t['relation']}::{t['object']}" for t in current_tuples}

                for t in self._original_tuples:
                    if f"{t['user']}::{t['relation']}::{t['object']}" not in new_set:
                        self._queue_outbox("DELETE", t)

                for t in current_tuples:
                    if f"{t['user']}::{t['relation']}::{t['object']}" not in old_set:
                        self._queue_outbox("WRITE", t)

            self._original_tuples = current_tuples

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            for t in self._generate_authz_tuples():
                self._queue_outbox("DELETE", t)
            super().delete(*args, **kwargs)

    def _queue_outbox(self, action, t):
        from .models import FGASyncOutbox
        from .tasks import process_fga_outbox_batch

        FGASyncOutbox.objects.create(
            action=action,
            user_id=t["user"],
            relation=t["relation"],
            object_id=t["object"],
        )

        # Fire Celery task only AFTER the local DB transaction fully commits
        transaction.on_commit(lambda: process_fga_outbox_batch.delay())


class FGAAuthorizedListMixin:
    """
    Mixin to filter DRF querysets based on OpenFGA list_objects API.
    Can be used with ListAPIView or ListCreateAPIView.
    """

    fga_object_type = None
    fga_list_relation = "reader"

    def get_authorized_ids(self) -> list[str]:
        if not self.fga_object_type:
            raise ValueError("You must define `fga_object_type` on the view.")

        client = get_fga_client()
        response = client.list_objects(
            ClientListObjectsRequest(
                user=self.request.fga_user,  # Provided by TraefikIdentityMiddleware
                relation=self.fga_list_relation,
                type=self.fga_object_type,
            )
        )

        prefix = f"{self.fga_object_type}:"
        return [obj_string.replace(prefix, "") for obj_string in response.objects]

    def get_queryset(self):
        # 1. Ask OpenFGA for the allowed IDs
        allowed_ids = self.get_authorized_ids()

        # 2. Filter the standard Django queryset safely
        return super().get_queryset().filter(id__in=allowed_ids)


class FGAViewMixin:
    """
    Structure-agnostic mixin for DRF Views.
    Handles Queryset Filtering (List), Parent Checks (Create),
    and Object Checks (Update/Delete/Detail).
    """

    # The developer defines this entirely based on their business logic!
    FGA_VIEW_SETTINGS: ClassVar[dict] = {
        "object_type": None,  # e.g., "document"
        "list_relation": None,  # Relation needed to see the list (e.g., "can_read_list")
        "detail_relations": {},  # Map of HTTP Method -> Relation (e.g., {"PUT": "can_update"})
        "create_parent": None,  # Dict defining parent requirements for POST
    }

    def _get_fga_user(self):
        """Assumes TraefikIdentityMiddleware has attached the user to the request."""
        fga_user = getattr(self.request, "fga_user", None)
        if not fga_user:
            raise PermissionDenied("Missing identity context.")
        return fga_user

    # ==========================================
    # HOOK 1: LISTING (Filter the Queryset)
    # ==========================================
    def get_queryset(self):
        queryset = super().get_queryset()

        # Only apply FGA filtering if this is a List request (no lookup kwarg present)
        # Detail requests will be handled by check_object_permissions to return proper 403s.
        if self.kwargs.get(self.lookup_field):
            return queryset

        config = getattr(self, "FGA_VIEW_SETTINGS", {})
        obj_type = config.get("object_type")
        list_relation = config.get("list_relation")

        if obj_type and list_relation:
            client = get_fga_client()
            response = client.list_objects(
                ClientListObjectsRequest(
                    user=self._get_fga_user(), relation=list_relation, type=obj_type
                )
            )
            prefix = f"{obj_type}:"
            allowed_ids = [obj.replace(prefix, "") for obj in response.objects]
            return queryset.filter(id__in=allowed_ids)

        return queryset

    # ==========================================
    # HOOK 2: CREATION (Check Parent Cascading)
    # ==========================================
    def check_permissions(self, request):
        super().check_permissions(request)

        config = getattr(self, "FGA_VIEW_SETTINGS", {})
        parent_config = config.get("create_parent")

        if request.method == "POST" and parent_config:
            parent_type = parent_config.get("parent_type")
            payload_field = parent_config.get("payload_field")
            relation = parent_config.get("relation")

            parent_id = request.data.get(payload_field)
            if not parent_id:
                raise PermissionDenied(f"Payload must include parent field: '{payload_field}'")

            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=self._get_fga_user(),
                    relation=relation,
                    object=f"{parent_type}:{parent_id}",
                )
            )
            if not response.allowed:
                raise PermissionDenied(
                    f"You must be '{relation}' on '{parent_type}' to create this object."
                )

    # ==========================================
    # HOOK 3: MUTATION/DETAIL (Check Object)
    # ==========================================
    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)

        config = getattr(self, "FGA_VIEW_SETTINGS", {})
        obj_type = config.get("object_type")
        detail_relations = config.get("detail_relations", {})

        relation = detail_relations.get(request.method)

        if obj_type and relation:
            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=self._get_fga_user(),
                    relation=relation,
                    object=f"{obj_type}:{obj.pk}",
                )
            )
            if not response.allowed:
                raise PermissionDenied(f"You do not have '{relation}' access to this object.")
