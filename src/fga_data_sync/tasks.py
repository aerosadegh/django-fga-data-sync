import logging
from collections.abc import Callable
from functools import wraps

from celery import shared_task
from django.db import transaction
from openfga_sdk.client.models import ClientTuple, ClientWriteRequest

from fga_data_sync.conf import get_setting
from fga_data_sync.utils import get_fga_client

logger = logging.getLogger(__name__)


def fga_retry_on_failure(func: Callable) -> Callable:
    """
    Decorator to handle retry logic for FGA sync operations.

    This decorator ensures that database updates (retry counts, status changes)
    are committed BEFORE triggering Celery retries. This prevents race conditions
    where a retry might execute before the database reflects the previous attempt.

    The pattern:
    1. Execute function within atomic transaction
    2. If exception occurs, update DB with retry metadata
    3. Commit transaction
    4. Raise retry exception AFTER commit

    Args:
        func: The Celery task function to wrap

    Returns:
        Wrapped function with safe retry behavior

    Example:
        @shared_task(bind=True)
        @fga_retry_on_failure
        def my_fga_task(self):
            # Your FGA sync logic here
            pass
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        retry_exc = None  # Capture exception to raise AFTER transaction commits

        with transaction.atomic():
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"FGA Sync operation failed: {e}")

                # Get pending tasks from the outbox to update their retry counts
                from fga_data_sync.models import FGASyncOutbox

                pending_tasks = list(
                    FGASyncOutbox.objects.select_for_update(skip_locked=True).filter(
                        status=FGASyncOutbox.Status.PENDING
                    )[: get_setting("BATCH_SIZE")]
                )

                # Update retry counts for all pending tasks
                for task in pending_tasks:
                    task.retry_count += 1
                    if task.retry_count >= self.max_retries:
                        task.status = FGASyncOutbox.Status.FAILED
                    task.save(update_fields=["retry_count", "status"])

                # Store the exception to raise it AFTER the DB commits
                retry_exc = e

        # ==========================================
        # OUTSIDE THE ATOMIC BLOCK
        # The database has safely committed.
        # Now we safely tell the Celery broker to retry the task.
        # ==========================================
        if retry_exc:
            countdown = 2**self.request.retries
            raise self.retry(exc=retry_exc, countdown=countdown)

    return wrapper


@shared_task(bind=True, max_retries=get_setting("MAX_RETRIES"))
@fga_retry_on_failure
def process_fga_outbox_batch(self):
    """
    Process a batch of pending FGA synchronization tasks from the outbox.

    This task implements the outbox pattern for reliable async synchronization
    with OpenFGA. It safely handles concurrent workers through row-level locking
    and provides exponential backoff retry logic on failures.

    The workflow:
    1. Lock and fetch pending tasks (skip_locked prevents worker contention)
    2. Batch tasks into WRITE/DELETE operations
    3. Send batch request to OpenFGA
    4. Update task statuses to SYNCED on success
    5. On failure: increment retry_count, mark as FAILED if max retries exceeded
    6. Retry with exponential backoff (2^retries seconds)

    Returns:
        str: Status message indicating number of tasks processed or reason for no-op

    Raises:
        Retry: Celery retry exception if batch processing fails (after DB commit)

    Note:
        - Uses select_for_update(skip_locked=True) to prevent multiple workers
          from processing the same tasks
        - BATCH_SIZE and MAX_RETRIES are configurable via settings
        - Failed tasks are marked FAILED after max_retries attempts
    """
    # Lock the rows to prevent other celery workers from executing the same tuples
    from fga_data_sync.models import FGASyncOutbox

    pending_tasks = list(
        FGASyncOutbox.objects.select_for_update(skip_locked=True).filter(
            status=FGASyncOutbox.Status.PENDING
        )[: get_setting("BATCH_SIZE")]
    )

    if not pending_tasks:
        return "No pending tasks."

    fga_client = get_fga_client()
    writes = []
    deletes = []

    for task in pending_tasks:
        fga_tuple = ClientTuple(user=task.user_id, relation=task.relation, object=task.object_id)
        if task.action == FGASyncOutbox.Action.WRITE:
            writes.append(fga_tuple)
        elif task.action == FGASyncOutbox.Action.DELETE:
            deletes.append(fga_tuple)

    # Send batch network request
    fga_client.write(ClientWriteRequest(writes=writes, deletes=deletes))

    # Fast bulk update of status
    task_ids = [t.id for t in pending_tasks]
    FGASyncOutbox.objects.filter(id__in=task_ids).update(status=FGASyncOutbox.Status.SYNCED)

    return f"Successfully synced {len(pending_tasks)} FGA tuples."
