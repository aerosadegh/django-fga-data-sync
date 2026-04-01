# fga_data_sync/mixins.py
import uuid
from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from openfga_sdk.client.models import ClientCheckRequest, ClientListObjectsRequest
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request

from fga_data_sync.adapters import FGATupleAdapter
from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.structs import FGAModelConfig, FGAViewConfig
from fga_data_sync.tasks import process_fga_outbox_batch
from fga_data_sync.utils import get_fga_client

__all__ = [
    "FGASyncMixin",
    "FGAViewMixin",
]


class FGASyncMixin:
    """
    Structure-agnostic mixin for synchronizing Django models to OpenFGA via the Outbox pattern.
    Requires `fga_config` to be defined on the model using `FGAModelConfig`.
    """

    fga_config: ClassVar[FGAModelConfig | None] = None
    pk: int | str | uuid.UUID | None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        # Delegate tuple generation to the adapter
        self._original_tuples = (
            FGATupleAdapter.generate_tuples(self, self.fga_config) if self.pk else []
        )
        self._fga_task_scheduled = False

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_new = self.pk is None

        with transaction.atomic():
            super().save(*args, **kwargs)  # type: ignore[misc]
            current_tuples = FGATupleAdapter.generate_tuples(self, self.fga_config)

            if is_new:
                for t in current_tuples:
                    self._queue_outbox(FGASyncOutbox.Action.WRITE, t)
            else:
                to_delete, to_write = FGATupleAdapter.compute_diffs(
                    self._original_tuples, current_tuples
                )

                for t in to_delete:
                    self._queue_outbox(FGASyncOutbox.Action.DELETE, t)

                for t in to_write:
                    self._queue_outbox(FGASyncOutbox.Action.WRITE, t)

            self._original_tuples = current_tuples

    def delete(self, *args: Any, **kwargs: Any) -> None:
        with transaction.atomic():
            for t in FGATupleAdapter.generate_tuples(self, self.fga_config):
                self._queue_outbox(FGASyncOutbox.Action.DELETE, t)
            super().delete(*args, **kwargs)  # type: ignore[misc]

    def _queue_outbox(self, action: str, t: dict[str, str]) -> None:
        FGASyncOutbox.objects.create(
            action=action,
            user_id=t["user"],
            relation=t["relation"],
            object_id=t["object"],
        )

        if not self._fga_task_scheduled:
            transaction.on_commit(lambda: process_fga_outbox_batch.delay())
            self._fga_task_scheduled = True


class FGAViewMixin:
    """
    Structure-agnostic mixin for DRF Views to enforce FGA Authorization.
    Requires `fga_config` of type `FGAViewConfig`.
    """

    fga_config: ClassVar[FGAViewConfig | None] = None

    request: Request
    kwargs: dict[str, Any]
    lookup_field: str

    def _get_fga_user(self) -> str:
        fga_user = getattr(self.request, "fga_user", None)
        if not fga_user:
            # Defensive fix: Missing identity is a 401 Authentication Failed, not 403.
            raise AuthenticationFailed("Missing identity context.")
        return fga_user

    def _get_config(self) -> FGAViewConfig:
        if not isinstance(self.fga_config, FGAViewConfig):
            raise ImproperlyConfigured("View must define `fga_config` of type `FGAViewConfig`.")
        return self.fga_config

    def get_queryset(self):
        queryset = super().get_queryset()
        view_kwargs = getattr(self, "kwargs", {})

        # Only apply FGA filtering if this is a List request
        if view_kwargs.get(self.lookup_field):
            return queryset

        config = self._get_config()
        if config.object_type and config.read_relation:
            client = get_fga_client()
            response = client.list_objects(
                ClientListObjectsRequest(
                    user=self._get_fga_user(),
                    relation=config.read_relation,
                    type=config.object_type,
                )
            )
            prefix = f"{config.object_type}:"
            allowed_ids = [obj.replace(prefix, "") for obj in response.objects]
            return queryset.filter(id__in=allowed_ids)

        return queryset

    def check_permissions(self, request: Request) -> None:
        super().check_permissions(request)  # type: ignore[misc]
        config = self._get_config()

        if request.method == "POST" and config.create_parent_type:
            parent_id = request.data.get(config.create_parent_field)
            if not parent_id:
                raise PermissionDenied(
                    f"Payload must include parent field: '{config.create_parent_field}'"
                )

            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=self._get_fga_user(),
                    relation=config.create_relation,
                    object=f"{config.create_parent_type}:{parent_id}",
                )
            )
            if not response.allowed:
                raise PermissionDenied(
                    f"You must be '{config.create_relation}' on '{config.create_parent_type}'"
                    " to create this object."
                )

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        super().check_object_permissions(request, obj)  # type: ignore[misc]
        config = self._get_config()

        relation = config.action_relations.get(request.method)
        if not relation:
            # Default fallback if standard methods are used instead of custom actions
            if request.method in ["PUT", "PATCH"]:
                relation = config.update_relation
            elif request.method == "DELETE":
                relation = config.delete_relation
            elif request.method == "GET":
                relation = config.read_relation

        if config.object_type and relation:
            client = get_fga_client()
            response = client.check(
                ClientCheckRequest(
                    user=self._get_fga_user(),
                    relation=relation,
                    object=f"{config.object_type}:{obj.pk}",
                )
            )
            if not response.allowed:
                raise PermissionDenied(f"You do not have '{relation}' access to this object.")
