# Django FGA Data Sync

A declarative, strictly-typed, Outbox-pattern OpenFGA synchronizer for Django models.

This package automatically translates your Django relational models into OpenFGA authorization graph tuples. It guarantees perfect synchronization between your local PostgreSQL database and your distributed OpenFGA server using the Transactional Outbox pattern and Celery.

## 📦 Installation

Install the package via pip or uv:

```bash
pip install django-fga-data-sync
```

Add it to your `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = [
    # ... your other apps ...
    'fga_data_sync',
]
```

Run migrations to create the Outbox table in your database:

```bash
python manage.py migrate fga_data_sync
```

## ⚙️ Configuration

Configure the package by adding the `AUTHZ_DATA_SYNC` dictionary to your `settings.py`.

```python
# settings.py

AUTHZ_DATA_SYNC = {
    # REQUIRED: The Store ID provisioned by the Central Auth Service
    "OPENFGA_STORE_ID": "01H...XYZ",

    # OPTIONAL: Defaults shown below
    "OPENFGA_API_URL": "http://localhost:8080",
    "BATCH_SIZE": 50,
    "MAX_RETRIES": 5,
}
```

## 💡 Usage

To synchronize a Django model with OpenFGA, simply inherit from `FGAModelSyncMixin` and define your `fga_config` using the `FGAModelConfig` dataclass. The package handles everything else automatically.

### Example: Defining Cascading Inheritance & Roles

```python
from django.db import models
from typing import ClassVar
from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGAModelConfig, FGAParentConfig, FGACreatorConfig

class Document(FGAModelSyncMixin, models.Model):
    title = models.CharField(max_length=255)

    # Soft references (No foreign keys required for FGA mapping!)
    folder_id = models.UUIDField()
    creator_id = models.UUIDField()

    fga_config: ClassVar[FGAModelConfig] = FGAModelConfig(
        object_type="document",
        parents=[
            FGAParentConfig(
                relation="folder",           # OpenFGA relation
                parent_type="folder",        # OpenFGA parent type
                local_field="folder_id"      # Django model field
            )
        ],
        creators=[
            FGACreatorConfig(
                relation="editor",           # OpenFGA explicit role
                local_field="creator_id"     # Django model field
            )
        ]
    )
```

Whenever you call `Document.objects.create()`, `document.save()`, or `document.delete()`, the mixin will automatically calculate the graph diffs, queue the tuples in the local Outbox table, and trigger the Celery worker to push them to OpenFGA asynchronously.

## 🕸️ Celery Configuration

Because this package uses the Transactional Outbox pattern, you must have Celery configured in your project to process the queued network requests.

The background task (`process_fga_outbox_batch`) is automatically triggered upon a successful database commit. However, as a fail-safe against broker crashes, you should configure a Celery Beat sweeper to run periodically:

```python
# celery.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    'fga-outbox-sweeper': {
        'task': 'fga_data_sync.tasks.process_fga_outbox_batch',
        'schedule': crontab(minute='*/5'), # Sweep the Outbox every 5 minutes
    },
}
```
