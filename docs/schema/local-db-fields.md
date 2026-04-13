## Database Schema vs. OpenFGA Graph: When do you need a local field?

When designing your system, you must decide which relationships live in your Django PostgreSQL database and which relationships live *exclusively* in OpenFGA.

The golden rule of this framework is: **The `FGAModelSyncMixin` can only synchronize data it can see.** If you define a relation in `FGAModelConfig`, there **must** be a corresponding physical field in your Django model.

Here is how to decide where a relationship belongs:

### 1. Relations that REQUIRE a field in your Django Model
You must add a `ForeignKey`, `UUIDField`, or `CharField` to your Django `models.py` when the relationship is a core structural property of the object or its initial birth state.

These are typically **1-to-1** or **Many-to-1** relationships. Because they exist in the Django database, the `FGAModelSyncMixin` will automatically read them and sync them to OpenFGA.

**Examples that need a Django field (`local_field`):**

- **Structural Parents:** A Document belongs to a Folder. You need a `folder_id` column so Django knows where to render it in the UI and how to perform cascading deletes.

- **The Initial Creator/Owner:** The user who literally clicked "Create." You need a `creator_id` column for basic audit trails.

```python
class Document(FGAModelSyncMixin, models.Model):
    title = models.CharField(max_length=255)

    # ⚠️ THESE REQUIRE DB COLUMNS
    folder_id = models.UUIDField()      # Structural Parent
    creator_id = models.UUIDField()     # Initial Owner

    fga_config = FGAModelConfig(
        object_type="document",
        parents=[FGAParentConfig(relation="folder", parent_type="folder", local_field="folder_id")],
        creators=[FGACreatorConfig(relation="owner", local_field="creator_id")]
    )
```

### 2. Relations that DO NOT require a field in your Django Model (FGA Handles It)

You should **not** add fields or Many-to-Many (M2M) tables to Django for highly dynamic, collaborative roles. OpenFGA is built to handle these natively, keeping your PostgreSQL database incredibly lean.

**Examples that DO NOT need a Django field:**

- **Reviewers:** A document can have 50 reviewers.
- **Editors/Viewers:** A document is shared with 100 different users.

Instead of bloating `models.py` with M2M junction tables, you write these relationships directly to the OpenFGA graph. Django never stores the fact that "Eve is a Reviewer." OpenFGA remembers it for you.

👉 **See the [Role Assignments Guide](./role-assignments.md) for full code examples on how to write these dynamic relationships directly to OpenFGA using ViewSets and custom actions.**


### 3. Handling One-to-Many (1:N) Relationships

In a One-to-Many relationship (e.g., One `Department` has Many `Employees`), the physical database column (`ForeignKey`) always lives on the "Many" side (the Child).

Because the `FGAModelSyncMixin` relies on reading physical columns, **you must place the `FGAModelConfig` on the Child model.** The Parent model does not need any FGA configuration to act as a structural parent!

### Example: A Department with Many Employees

Let's say a Department Head automatically gets "viewer" access to all Employees within their Department. OpenFGA handles this through inheritance. We just need to tell OpenFGA that the Employee belongs to the Department.

```python
from django.db import models
from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGAModelConfig, FGAParentConfig

# 1. The "One" Side (Parent)
class Department(models.Model):
    name = models.CharField(max_length=255)
    # Notice: No FGAModelSyncMixin is required here if it's just acting as a parent!

# 2. The "Many" Side (Child)
class Employee(FGAModelSyncMixin, models.Model):
    name = models.CharField(max_length=255)

    # The physical database column
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="employees")

    # The OpenFGA Graph Mapping goes on the CHILD
    fga_config = FGAModelConfig(
        object_type="employee",
        parents=[
            FGAParentConfig(
                relation="department",          # The FGA relationship
                parent_type="department",       # The FGA parent type
                local_field="department_id"     # The Django DB column
            )
        ]
    )
```

**How it works:**
Whenever a new `Employee` is created, the mixin reads the `department_id` from the Employee record and tells OpenFGA: `department:{id}` is the `department` of `employee:{id}`. OpenFGA takes care of the rest, automatically granting the Department Head access to the new employee.


## Mapping a Django ForeignKey to OpenFGA

When your Django model uses a `models.ForeignKey` to establish a structural parent, you must tell the `FGAModelSyncMixin` how to read it.

### The "Django Magic" Rule (`_id`)
When you define a `ForeignKey` in Django (e.g., `folder = models.ForeignKey(...)`), Django automatically creates an underlying database column and property with an `_id` suffix (e.g., `folder_id`).

**You must use this `_id` property as the `local_field` in your `FGAParentConfig`.** Do not use the related object name itself, as that would force the mixin to perform an unnecessary SQL JOIN just to read the ID!

### Example: A Document inside a Folder

Here is a complete example of a Django model with a strict physical relationship (a ForeignKey) perfectly mapped to an OpenFGA structural relationship.

```python
from django.db import models
from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGAModelConfig, FGAParentConfig

# 1. The Parent Model
class Folder(models.Model):
    name = models.CharField(max_length=255)

# 2. The Child Model
class Document(FGAModelSyncMixin, models.Model):
    title = models.CharField(max_length=255)

    # THE PHYSICAL DATABASE COLUMN:
    # Django will automatically create a property called `folder_id`
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="documents")

    # THE OPENFGA GRAPH MAPPING:
    fga_config = FGAModelConfig(
        object_type="document",
        parents=[
            FGAParentConfig(
                relation="parent",           # The OpenFGA relationship name
                parent_type="folder",        # The OpenFGA type of the parent
                local_field="folder_id"      # <--- The exact Django DB column property!
            )
        ]
    )
```

### How the Mixin processes this:
When you execute `document.save()`, the mixin does **not** fetch the related `Folder` object from the database. Instead, it highly efficiently reads `self.folder_id` directly from memory and generates the following tuple:

* **User:** `folder:{folder_id}`
* **Relation:** `parent`
* **Object:** `document:{id}`

By mapping the configuration to the `_id` field, you maintain strict referential integrity in your PostgreSQL database while allowing OpenFGA to perfectly mirror that hierarchy in the authorization graph.
