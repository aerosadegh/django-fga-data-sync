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

### Method 1: Programmatically (API/Views)
Use the service utility to assign roles programmatically. This instantly fires a payload to the OpenFGA server.

```python
from fga_manager.services import assign_mini_app_role
from users.models import User

bob = User.objects.get(email="bob@example.com")

assign_mini_app_role(
    user_uuid=bob.id, 
    mini_app_slug="your_app_slug", 
    role="manager",                
    resource_type="organization",  
    resource_id="org_777"          
)
```

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
