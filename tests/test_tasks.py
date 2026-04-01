# tests/test_tasks.py
import pytest

from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.tasks import process_fga_outbox_batch

pytestmark = pytest.mark.django_db


class TestProcessOutboxBatch:
    def test_successful_batch_sync(self, mock_fga_client):
        """Verifies pending tasks are gathered, sent to FGA, and marked as Synced."""
        # Create dummy pending tasks
        task1 = FGASyncOutbox.objects.create(
            action=FGASyncOutbox.Action.WRITE,
            user_id="user:1",
            relation="viewer",
            object_id="doc:1",
        )
        task2 = FGASyncOutbox.objects.create(
            action=FGASyncOutbox.Action.DELETE,
            user_id="user:2",
            relation="editor",
            object_id="doc:2",
        )

        # Execute the Celery task synchronously
        result = process_fga_outbox_batch()

        # 1. Verify the task output
        assert result == "Successfully synced 2 FGA tuples."

        # 2. Verify the SDK was called with the correct formatted payloads
        mock_fga_client.write.assert_called_once()
        write_request = mock_fga_client.write.call_args[0][0]

        assert len(write_request.writes) == 1
        assert write_request.writes[0].user == "user:1"

        assert len(write_request.deletes) == 1
        assert write_request.deletes[0].user == "user:2"

        # 3. Verify the database state mutated correctly
        task1.refresh_from_db()
        task2.refresh_from_db()
        assert task1.status == FGASyncOutbox.Status.SYNCED
        assert task2.status == FGASyncOutbox.Status.SYNCED

    def test_batch_sync_failure_and_retry(self, mock_fga_client, mocker):
        """Verifies that a network failure triggers a Celery retry and updates retry_count."""
        from celery.exceptions import Retry

        task1 = FGASyncOutbox.objects.create(
            action=FGASyncOutbox.Action.WRITE,
            user_id="user:1",
            relation="viewer",
            object_id="doc:1",
        )

        # 1. Force the OpenFGA mock to throw a Network Exception
        mock_fga_client.write.side_effect = Exception("FGA Server Down")

        # 2. Intercept Celery's retry mechanism so we can catch the exception safely
        mocker.patch("fga_data_sync.tasks.process_fga_outbox_batch.retry", side_effect=Retry)

        with pytest.raises(Retry):
            process_fga_outbox_batch()

        # 3. Verify the database recorded the failed attempt
        task1.refresh_from_db()
        assert task1.retry_count == 1
        assert task1.status == FGASyncOutbox.Status.PENDING  # Still pending, will retry later

    def test_batch_sync_max_retries_failure(self, mock_fga_client, mocker):
        """Verifies that exceeding max retries sets the status to FAILED."""
        from celery.exceptions import Retry

        task1 = FGASyncOutbox.objects.create(
            action=FGASyncOutbox.Action.WRITE,
            user_id="user:1",
            relation="viewer",
            object_id="doc:1",
            retry_count=4,  # Max retries is 5, so this attempt will be the last one
        )

        mock_fga_client.write.side_effect = Exception("FGA Server Down")
        mocker.patch("fga_data_sync.tasks.process_fga_outbox_batch.retry", side_effect=Retry)

        with pytest.raises(Retry):
            process_fga_outbox_batch()

        # The task gave up, so status should now permanently be FAILED
        task1.refresh_from_db()
        assert task1.retry_count == 5
        assert task1.status == FGASyncOutbox.Status.FAILED
