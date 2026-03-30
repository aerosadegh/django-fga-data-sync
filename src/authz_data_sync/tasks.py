import logging

from celery import shared_task
from django.db import transaction
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest

from authz_data_sync.conf import get_setting

from .models import FGASyncOutbox
from .utils import get_fga_client

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=get_setting("MAX_RETRIES"))
def process_fga_outbox_batch(self):
    """
    Sweeps the Outbox for pending tasks, batches them (up to 50), and pushes to OpenFGA.
    """
    with transaction.atomic():
        # Lock the rows to prevent other celery workers from executing the same tuples
        pending_tasks = list(
            FGASyncOutbox.objects.select_for_update(skip_locked=True).filter(status="PENDING")[
                : get_setting("BATCH_SIZE")
            ]
        )

        if not pending_tasks:
            return "No pending tasks."

        fga_client = get_fga_client()
        writes = []
        deletes = []

        for task in pending_tasks:
            fga_tuple = ClientTuple(
                user=task.user_id, relation=task.relation, object=task.object_id
            )
            if task.action == "WRITE":
                writes.append(fga_tuple)
            elif task.action == "DELETE":
                deletes.append(fga_tuple)

        try:
            # Send batch network request
            fga_client.write(ClientWriteRequest(writes=writes, deletes=deletes))

            # Fast bulk update of status
            task_ids = [t.id for t in pending_tasks]
            FGASyncOutbox.objects.filter(id__in=task_ids).update(status="SYNCED")

            return f"Successfully synced {len(pending_tasks)} FGA tuples."

        except Exception as e:
            logger.error(f"FGA Sync Batch Failed: {e}")

            for task in pending_tasks:
                task.retry_count += 1
                if task.retry_count >= self.max_retries:
                    task.status = "FAILED"
                task.save(update_fields=["retry_count", "status"])

            # Exponential Backoff
            countdown = 2**self.request.retries
            raise self.retry(exc=e, countdown=countdown) from e
