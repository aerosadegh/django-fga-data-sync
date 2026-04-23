## Frontend Integration (Serializers)

A seamless user experience requires the frontend UI (React, Vue, etc.) to know exactly what actions a user is allowed to perform. Relying on HTTP `403 Forbidden` errors after a user clicks a button is an anti-pattern. The frontend needs to know in advance whether to render, disable, or hide action buttons (like "Edit" or "Delete").

To solve this, `django-fga-data-sync` provides the `FGAPermissionSerializerMixin`. It automatically evaluates OpenFGA roles and injects a `_permissions` dictionary directly into your Django REST Framework (DRF) JSON payloads.

### Quickstart

To expose FGA permissions to your frontend, simply inherit from `FGAPermissionSerializerMixin` and define your FGA configurations in the `Meta` class.

> **Note:** Use tuples `()` instead of lists `[]` for `fields` and `fga_permissions` to comply with Python strict mutability linters (like Ruff's `RUF012`).

```python
from rest_framework import serializers
from fga_data_sync import FGAPermissionSerializerMixin
from .models import Project

class ProjectSerializer(FGAPermissionSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Project
        # The mixin automatically injects "_permissions" into this tuple for you!
        fields = ("id", "name", "company_id")

        # 1. Define the OpenFGA object type for this model
        fga_object_type = "project"

        # 2. Define the exact permissions you want to expose to the frontend
        fga_permissions = ("can_update_project", "can_delete_project")
```

### The JSON Payload

When the frontend fetches this endpoint, the mixin safely appends the evaluations:

```json
{
  "id": 101,
  "name": "Frontend Redesign",
  "company_id": 5,
  "_permissions": {
    "can_update_project": true,
    "can_delete_project": false
  }
}
```
Your frontend developers can now conditionally render UI components with zero business logic:
```jsx
{project._permissions.can_delete_project && <DeleteButton />}
```

### High-Performance Batching (Preventing N+1 Queries)

Evaluating permissions for a list of 50 items could easily result in 50 separate HTTP requests to your OpenFGA server, causing massive network bottlenecks (The N+1 Problem).

**The mixin solves this automatically.** When a DRF list view requests multiple items (`many=True`), the mixin secretly swaps in a custom `FGABatchListSerializer`. This batcher intercepts the dataset, aggregates every permission check for every item, and makes **one single sub-millisecond `BatchCheck` network call** to OpenFGA. It then maps the results back to the individual items seamlessly.

You get perfect performance with zero extra configuration.

### Security Note: Is exposing permissions safe?

**Yes.** The `_permissions` object in the JSON payload is strictly for **Presentation UX** (knowing what buttons to draw on the screen).

The frontend is an untrusted environment. A malicious user could alter the frontend memory to force the "Delete" button to appear. However, true authorization lives in the backend. If that user clicks the hacked button and sends a `DELETE /api/projects/1/` request, your views (protected by `FGAViewMixin` or `IsFGAAuthorized`) will independently evaluate the action against the OpenFGA server and return a hard `403 Forbidden` before any data is altered.
