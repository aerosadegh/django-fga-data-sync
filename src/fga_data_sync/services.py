from django.db import transaction

from .models import FGASyncOutbox
from .tasks import process_fga_outbox_batch


class FGATupleIngestionService:
    """Service for consuming external events (like RabbitMQ) into the FGA Outbox."""

    @staticmethod
    def queue_tuple(action: FGASyncOutbox.Action, user: str, relation: str, fga_object: str):
        with transaction.atomic():
            FGASyncOutbox.objects.create(
                action=action, user_id=user, relation=relation, object_id=fga_object
            )
            # Trigger the celery worker just like the mixin does
            transaction.on_commit(lambda: process_fga_outbox_batch.delay())
