# Syncing Models to OpenFGA

To synchronize a Django model with OpenFGA, simply inherit from `AuthzSyncMixin` and define your `FGA_SETTINGS` dictionary. The package handles everything else automatically.

### Example: Defining Cascading Inheritance & Roles

```python
from django.db import models
from authz_data_sync.mixins import AuthzSyncMixin
from typing import ClassVar

class Document(AuthzSyncMixin, models.Model):
    title = models.CharField(max_length=255)     
    # Soft references (No foreign keys required for Authz mapping!)
    folder_id = models.UUIDField()     
    creator_id = models.UUIDField()     
    
    FGA_SETTINGS: ClassVar[dict] = {         
        "object_type": "document",         
        "parents": [             
            {
                "relation": "folder",           # OpenFGA relation
                "parent_type": "folder",        # OpenFGA parent type
                "local_field": "folder_id"      # Django model field
            }
        ],
        "creators": [             {
                "relation": "editor",           # OpenFGA explicit role
                "local_field": "creator_id"     # Django model field
            }
        ]
    }
```

Whenever you call `Document.objects.create()`, `document.save()`, or `document.delete()`, the mixin will automatically calculate the graph diffs, queue the tuples in the local Outbox table, and trigger the Celery worker to push them to OpenFGA asynchronously.