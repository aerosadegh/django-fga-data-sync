from django.db import models


class FGASyncOutbox(models.Model):
    class Status(models.TextChoices):
        # Database Value, Human Readable Label
        PENDING = "PENDING", "Pending"
        SYNCED = "SYNCED", "Synced"
        FAILED = "FAILED", "Failed"

    class Action(models.TextChoices):
        # Database Value, Human Readable Label
        WRITE = "WRITE", "Write"
        DELETE = "DELETE", "Delete"

    # max_length=7 covers "DELETE" (6 chars) with 1 char buffer for safety
    action = models.CharField(max_length=7, choices=Action.choices)
    user_id = models.CharField(max_length=255)
    relation = models.CharField(max_length=100)
    object_id = models.CharField(max_length=255)

    status = models.CharField(
        max_length=7, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FGA Sync Task"
        verbose_name_plural = "FGA Sync Tasks"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.action} {self.relation} for {self.object_id} ({self.status})"
