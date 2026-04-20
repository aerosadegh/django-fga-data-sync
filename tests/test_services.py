# tests/test_services.py
from unittest.mock import patch

import pytest

from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.services import FGATupleIngestionService

# 🤠 CRITICAL: transaction=True is required for testing transaction.on_commit() hooks!
# Without this, pytest rolls back the database before the commit hook ever fires.
pytestmark = pytest.mark.django_db(transaction=True)


class TestFGATupleIngestionService:
    @patch("fga_data_sync.services.process_fga_outbox_batch.delay")
    def test_queue_tuple_creates_record_and_triggers_task(self, mock_delay):
        """
        Verifies that consuming an external event safely writes to the Outbox
        and immediately notifies the Celery worker.
        """
        # Ensure outbox is empty before test
        FGASyncOutbox.objects.all().delete()

        # Execute the Service logic
        FGATupleIngestionService.queue_tuple(
            action=FGASyncOutbox.Action.WRITE,
            user="user:external_worker_99",
            relation="viewer",
            fga_object="document:777",
        )

        # 1. Mathematical Proof of Database Integrity
        # Assert the record was saved flawlessly
        assert FGASyncOutbox.objects.count() == 1

        task = FGASyncOutbox.objects.get()
        assert task.action == FGASyncOutbox.Action.WRITE
        assert task.user_id == "user:external_worker_99"
        assert task.relation == "viewer"
        assert task.object_id == "document:777"
        assert task.status == FGASyncOutbox.Status.PENDING

        # 2. Mathematical Proof of Async Trigger
        # Assert that the Celery task was successfully queued upon transaction commit
        mock_delay.assert_called_once()
