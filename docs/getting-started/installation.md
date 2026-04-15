# Installation & Setup

## 1. Install the Package

Install the package via pip or uv:

```bash
pip install django-fga-data-sync
```
or
```bash
uv add django-fga-data-sync
```

Add it to your `INSTALLED_APPS` and configure the Traefik middleware in your `settings.py`:

```python
INSTALLED_APPS = [
    # ... your other apps ...
    'fga_data_sync',
]

MIDDLEWARE = [
    # ...
    # Dynamically maps gateway headers to request attributes
    'fga_data_sync.middleware.TraefikIdentityMiddleware',
]
```

Run migrations to create the Outbox table in your database:

```bash
python manage.py migrate fga_data_sync
```

## 2. Configuration

Configure the package by adding the `FGA_DATA_SYNC` dictionary to your `settings.py`.

```python
FGA_DATA_SYNC = {
    # REQUIRED: The Store ID provisioned by the Central Auth Service
    "OPENFGA_STORE_ID": "01H...XYZ",

    # OPTIONAL: Defaults shown below
    "OPENFGA_API_URL": "http://localhost:8080",
    "BATCH_SIZE": 50,
    "MAX_RETRIES": 5,

    # DYNAMIC MAPPINGS: Map any gateway header to any request attribute!
    "REQUEST_HEADER_MAPPINGS": {
        # Required
        "X-User-Id": "fga_user",
        # Optionals
        "X-Context-Org-Id": "fga_tenant",
    },
    "FGA_USER_ATTR": "fga_user",
}
```

## 3. Celery Configuration

Because this package uses the Transactional Outbox pattern, you must have Celery configured in your project to process the queued network requests.

The background task (`process_fga_outbox_batch`) is automatically triggered upon a successful database commit. However, as a fail-safe against broker crashes, you should configure a Celery Beat sweeper to run periodically:

```python
# <project_name>/celery.py
import os

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "<project_name>.settings")

app = Celery("<project_name>")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix in settings.py.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
```

And for Celery Beat add this task in the `settings.py`:
```python
CELERY_BEAT_SCHEDULE = {
    "fga-outbox-sweeper": {
        "task": "fga_data_sync.tasks.process_fga_outbox_batch",
        "schedule": 300.0,  # Sweep the Outbox every 5 minutes
    },
    ...
}
```
