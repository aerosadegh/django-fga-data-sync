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
    'fga_data_sync.middleware.TraefikIdentityMiddleware', # Automatically extracts X-User-Id
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
}
```

## 3. Celery Configuration

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
