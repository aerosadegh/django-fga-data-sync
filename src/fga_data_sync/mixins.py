# fga_data_sync/mixins.py
import uuid
from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from openfga_sdk.client.models import ClientCheckRequest, ClientListObjectsRequest
from openfga_sdk.exceptions import ValidationException
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request
from rest_framework.viewsets import ViewSetMixin

from .adapters import FGATupleAdapter
from .conf import get_setting
from .loggers import FGAConsoleLogger
from .models import FGASyncOutbox
from .structs import FGAModelConfig, FGAViewConfig
from .tasks import process_fga_outbox_batch
from .utils import get_fga_client

__all__ = [
    "FGAModelSyncMixin",
    "FGAViewMixin",
]

logger = FGAConsoleLogger(__name__)


class FGAModelSyncMixin:
    """Structure-agnostic mixin for synchronizing Django models to OpenFGA via the Outbox pattern.

    This mixin intercepts the standard Django `save()` and `delete()` lifecycles.
    It utilizes the defined `FGAModelConfig` to calculate the exact OpenFGA tuple
    differences (diffs) and safely queues them in the local database transaction.

    Attributes:
        fga_config: The strict configuration class defining how this model maps
                    to the OpenFGA graph. Must be an instance of `FGAModelConfig`.
        pk: The primary key of the model instance.

    Example:
        **Basic Creator Ownership:**
        ```python
        from django.db import models
        from fga_data_sync.structs import FGAModelConfig, FGACreatorConfig

        class Document(FGAModelSyncMixin, models.Model):
            title = models.CharField(max_length=255)
            creator_id = models.CharField(max_length=255)

            fga_config = FGAModelConfig(
                object_type="document",
                creators=[
                    FGACreatorConfig(
                        relation="editor",
                        local_field="creator_id"
                    )
                ]
            )
        ```

        **Parent Hierarchies (Cascading):**
        ```python
        from fga_data_sync.structs import FGAParentConfig

        class Folder(FGAModelSyncMixin, models.Model):
            name = models.CharField(max_length=255)
            org_id = models.CharField(max_length=255)
            creator_id = models.CharField(max_length=255)

            fga_config = FGAModelConfig(
                object_type="folder",
                parents=[
                    FGAParentConfig(
                        relation="organization",
                        parent_type="organization",
                        local_field="org_id"
                    )
                ],
                creators=[
                    FGACreatorConfig(
                        relation="owner",
                        local_field="creator_id"
                    )
                ]
            )
        ```

        **Custom Role Assignment (Escape Hatch):**
        If you need to assign FGA roles based on dynamic data state (like a boolean field),
        you can intercept `save()` and manually queue tuples into the Outbox:
        ```python
        from fga_data_sync.models import FGASyncOutbox

        class Article(FGAModelSyncMixin, models.Model):
            title = models.CharField(max_length=255)
            is_public = models.BooleanField(default=False)

            fga_config = FGAModelConfig(object_type="article")

            def save(self, *args, **kwargs):
                # 1. Let the mixin handle the standard config-based tuples first
                super().save(*args, **kwargs)

                # 2. Inject your custom, dynamic logic
                if self.is_public:
                    self._queue_outbox(
                        action=FGASyncOutbox.Action.WRITE.value,
                        t={
                            "user": "user:*",  # OpenFGA wildcard for 'everyone'
                            "relation": "viewer",
                            "object": f"article:{self.pk}"
                        }
                    )
        ```

    Notes:
        **Limitations:**
        Because this mixin relies on intercepting the `save()` method for the
        Transactional Outbox pattern, standard Django bulk operations
        (e.g., `Document.objects.bulk_create()`) will bypass this mixin.
        You must save instances individually or trigger the outbox manually
        for bulk operations.
    """

    fga_config: ClassVar[FGAModelConfig | None] = None
    pk: int | str | uuid.UUID | None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if self.fga_config is None:
            raise ImproperlyConfigured(
                f"'{self.__class__.__name__}' must define an 'fga_config' attribute."
            )
        # Delegate tuple generation to the adapter
        self._original_tuples = (
            FGATupleAdapter.generate_tuples(self, self.fga_config) if self.pk else []
        )
        self._fga_task_scheduled = False

    def save(self, *args: Any, **kwargs: Any) -> None:
        is_new = self._state.adding  # type: ignore[attr-defined]

        with transaction.atomic():
            super().save(*args, **kwargs)  # type: ignore[misc]
            if self.fga_config is None:
                raise ImproperlyConfigured(
                    f"'{self.__class__.__name__}' must define an 'fga_config' attribute."
                )
            current_tuples = FGATupleAdapter.generate_tuples(self, self.fga_config)

            if is_new:
                for t in current_tuples:
                    self._queue_outbox(FGASyncOutbox.Action.WRITE, t)  # type: ignore[arg-type]
            else:
                to_delete, to_write = FGATupleAdapter.compute_diffs(
                    self._original_tuples, current_tuples
                )

                for t in to_delete:
                    self._queue_outbox(FGASyncOutbox.Action.DELETE, t)  # type: ignore[arg-type]

                for t in to_write:
                    self._queue_outbox(FGASyncOutbox.Action.WRITE, t)  # type: ignore[arg-type]

            self._original_tuples = current_tuples

    def delete(self, *args: Any, **kwargs: Any) -> None:
        with transaction.atomic():
            if self.fga_config is None:
                raise ImproperlyConfigured(
                    f"'{self.__class__.__name__}' must define an 'fga_config' attribute."
                )
            for t in FGATupleAdapter.generate_tuples(self, self.fga_config):
                self._queue_outbox(FGASyncOutbox.Action.DELETE, t)  # type: ignore[arg-type]
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
    """Structure-agnostic mixin for DRF Views to enforce OpenFGA Authorization.

    This mixin automatically handles three critical authorization lifecycle hooks
    in Django REST Framework without requiring manual permission logic:

    1. Queryset Filtering (`get_queryset`): Injects `id__in` filters on list views.
    2. Parent Verification (`check_permissions`): Checks required parent roles on POST requests.
    3. Object Verification (`check_object_permissions`): Checks specific object roles on
       PUT/PATCH/DELETE.

    Attributes:
        fga_config: The strict configuration class defining the authorization rules
                    for this view. Must be an instance of `FGAViewConfig`.

    Example:
        ```python
        from rest_framework import viewsets
        from fga_data_sync.structs import FGAViewConfig

        class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
            queryset = Document.objects.all()
            serializer_class = DocumentSerializer

            fga_config = FGAViewConfig(
                object_type="document",
                read_relation="can_read_document",
                update_relation="can_update",
                delete_relation="can_delete"
            )
        ```

    Raises:
        ImproperlyConfigured: If `fga_config` is missing, invalid, or utilizes
                              ViewSet-only features (like `action_relations`) on
                              a standard Generic View.
        AuthenticationFailed: If the Traefik identity header is missing.
        PermissionDenied: If the OpenFGA network check denies access.
    """

    fga_config: ClassVar[FGAViewConfig | None] = None

    request: Request
    kwargs: dict[str, Any]
    lookup_field: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # 🛡️ THE GUARDRAIL: Check for duplicate authorization strategies
        from fga_data_sync.permissions import IsFGAAuthorized

        permission_classes = getattr(self, "permission_classes", [])
        if IsFGAAuthorized in permission_classes:
            # The FGAConsoleLogger handles all the colors and prefixes.
            logger.warning(
                f"Duplicate FGA Authorization detected on '{self.__class__.__name__}'. "
                f"You are using both 'FGAViewMixin' and 'IsFGAAuthorized'. "
                f"This will result in redundant network calls to OpenFGA. "
                f"Please remove 'IsFGAAuthorized' from 'permission_classes'."
            )

    def _get_fga_user(self) -> str:
        user_attr = get_setting("FGA_USER_ATTR")
        fga_user = getattr(self.request, user_attr, None)
        if not fga_user:
            raise AuthenticationFailed(f"Missing identity context on '{user_attr}'.")
        return fga_user

    def _get_config(self) -> FGAViewConfig:
        if not isinstance(self.fga_config, FGAViewConfig):
            raise ImproperlyConfigured("View must define `fga_config` of type `FGAViewConfig`.")

        # 🛡️ THE GUARDRAIL: Fail fast on Dead Configuration
        if self.fga_config.action_relations and not isinstance(self, ViewSetMixin):
            raise ImproperlyConfigured(
                f"View '{self.__class__.__name__}' defines 'action_relations' in its "
                f"FGAViewConfig, but it is not a ViewSet. Standard Generic Views "
                "do not support @action decorators."
            )

        return self.fga_config

    def get_queryset(self):
        queryset = super().get_queryset()
        view_kwargs = getattr(self, "kwargs", {})

        # 1. Bypass if this is a Detail request (e.g., /api/companies/1/)
        if view_kwargs.get(self.lookup_field):
            return queryset

        config = self._get_config()

        # Explicitly bypass FGA filtering if the developer requested an open list
        if config.disable_list_filter:
            return queryset

        # 3. Fallback logic for backward compatibility
        relation_to_check = config.list_relation or config.read_relation

        # 4. Perform the OpenFGA network check
        if config.object_type and relation_to_check:
            client = get_fga_client()
            try:
                response = client.list_objects(
                    ClientListObjectsRequest(
                        user=self._get_fga_user(),
                        relation=relation_to_check,
                        type=config.object_type,
                    )
                )
            except ValidationException as e:
                error_msg = (
                    f"FGA DSL Mismatch: The relation '{relation_to_check}' on type "
                    f"'{config.object_type}' does not exist in your OpenFGA schema. "
                    f"Please update your DSL or fix your FGAViewConfig."
                )
                logger.error(error_msg)
                raise ImproperlyConfigured(error_msg) from e

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
            if config.create_relation is None:
                raise ImproperlyConfigured("FGAViewConfig must have all `create_*` keys together.")

            client = get_fga_client()
            try:
                response = client.check(
                    ClientCheckRequest(
                        user=self._get_fga_user(),
                        relation=config.create_relation,
                        object=f"{config.create_parent_type}:{parent_id}",
                    )
                )
            except ValidationException as e:
                error_msg = (
                    f"FGA DSL Mismatch: The relation '{config.create_relation}' on type "
                    f"'{config.create_parent_type}' does not exist in your OpenFGA schema. "
                    f"Please update your DSL or fix your FGAViewConfig."
                )
                logger.error(error_msg)
                raise ImproperlyConfigured(error_msg) from e

            if not response.allowed:
                raise PermissionDenied(
                    f"You must be '{config.create_relation}' on '{config.create_parent_type}'"
                    " to create this object."
                )
            return  # Early return for POST creation

        if config.lookup_header or config.lookup_url_kwarg:
            self.check_object_permissions(request, obj=None)

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        super().check_object_permissions(request, obj)  # type: ignore[misc]
        config = self._get_config()

        relation: str | None = None

        # 1. Resolve relation via Custom ViewSet Action
        view_action: str | None = getattr(self, "action", None)
        if view_action:
            relation = config.action_relations.get(view_action)

        # 2. Default fallback if standard methods are used instead of custom actions
        if not relation:
            if request.method in ["PUT", "PATCH"]:
                relation = config.update_relation
            elif request.method == "DELETE":
                relation = config.delete_relation
            elif request.method in ["GET", "OPTIONS", "HEAD"]:
                relation = config.read_relation

        if config.object_type and relation:
            client = get_fga_client()
            try:
                response = client.check(
                    ClientCheckRequest(
                        user=self._get_fga_user(),
                        relation=relation,
                        object=f"{config.object_type}:{obj.pk}",
                    )
                )
            except ValidationException as e:
                error_msg = (
                    f"FGA DSL Mismatch: The relation '{relation}' on type "
                    f"'{config.object_type}' does not exist in your OpenFGA schema. "
                    f"Please update your DSL or fix your FGAViewConfig."
                )
                logger.error(error_msg)
                raise ImproperlyConfigured(error_msg) from e
            if not response.allowed:
                raise PermissionDenied(f"You do not have '{relation}' access to this object.")
