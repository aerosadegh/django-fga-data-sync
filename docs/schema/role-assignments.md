# Role Assignments & Tuple Injection

Because `django-authz-data-sync` bridges Django and OpenFGA, your Django core does not need to hardcode complex hierarchical logic. It simply passes structural strings directly to the OpenFGA graph.

## How FGA Graph Traversal Works
When inviting a user to a specific resource (like a `folder`), you **do not** need to include the parent `organization_id` in your API payload.

When the `folder` was originally created, a **Structural Tuple** was injected into OpenFGA linking the `folder` to the `organization`. Because of this, OpenFGA automatically climbs the graph tree to check permissions. Your frontend only ever needs to pass the exact resource it is interacting with:

```json
// Scenario: Inviting a user to a Child Concept (e.g., Folder)
{
    "username": "alice_smith",
    "mini_app_slug": "doc",
    "role": "contributor",
    "resource_type": "folder",
    "resource_id": "folder_99"
}
```

## Assigning Roles

There are two primary ways to make a user a Manager of an Organization (or any other role).

### Method 1: Programmatically (API/Views/Services)
You can directly interact with the `FGASyncOutbox` model to queue your own custom tuples. Because the Celery worker sweeps the Outbox entirely independently of how the records got there, this is the safest way to assign roles outside the standard model creation lifecycle.

```python
from fga_data_sync.models import FGASyncOutbox
from users.models import User

bob = User.objects.get(email="bob@example.com")

# 1. Manually queue the Role Assignment directly into the Outbox!
FGASyncOutbox.objects.create(
    action=FGASyncOutbox.Action.WRITE.value,
    user_id=f"user:{bob.id}",
    relation="manager",
    object_id="organization:org_777"
)

# 2. Optionally, trigger the Celery worker to wake up immediately
from fga_data_sync.tasks import process_fga_outbox_batch
process_fga_outbox_batch.delay()
```

***

### The "Why" behind these architectural fixes:
* **Type Safety Enforcement:** Updating the docs to reflect `FGAModelConfig` and `FGAViewConfig` ensures developers leverage your IDE-friendly, validated data classes. This catches misconfigurations at import-time rather than runtime.
* **Single Source of Truth:** By consolidating view-level permission attributes inside the `FGAViewConfig`, the views remain pristine and the documentation correctly reflects the DRY (Don't Repeat Yourself) principle.
* **Native Infrastructure Utilization:** The `FGASyncOutbox` model educates developers on how to leverage the Transactional Outbox pattern manually. This guarantees eventual consistency even for custom business logic.

### Method 2: Manually (Django Admin)
You can also use the **User Role Assignment** proxy table in the Django Admin panel to manually upgrade a user's permissions.

## The Tuple Injection Cheat Sheet

When creating new entities, you must fire off exact tuples to keep the OpenFGA graph perfectly connected. Note that in strict DSLs, powerful roles like `superadmin` might only be inheritable from the platform and cannot be explicitly assigned at the organization level.

**1. Creating a New Organization**
Link the organization to the global platform.
```python
tuples = [
    {"user": "platform:1", "relation": "platform", "object": f"organization:{org.id}"},
    {"user": f"user:{alice.id}", "relation": "admin", "object": f"organization:{org.id}"}
]
```

**2. Creating a New Folder**
Link the Folder to the Organization.
```python
tuples = [
    {"user": f"organization:{org.id}", "relation": "organization", "object": f"folder:{folder.id}"},
    {"user": f"user:{bob.id}", "relation": "owner", "object": f"folder:{folder.id}"}
]
```
