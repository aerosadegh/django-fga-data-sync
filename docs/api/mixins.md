
# Mixins

::: fga_data_sync.mixins
    options:
      show_root_heading: true



### 🏗️ The Multi-Parent & Multi-Creator Architecture

Imagine a scenario where a `Document` belongs to both a `Folder` and a `Project` (Multiple Parents). Furthermore, when it is created, it assigns both an `author` and an initial `reviewer` (Multiple Creators).

Here is the perfect example to add to your documentation or docstrings:

```python
from django.db import models
from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGAModelConfig, FGAParentConfig, FGACreatorConfig

class Document(FGAModelSyncMixin, models.Model):
    title = models.CharField(max_length=255)

    # Structural Links (Multiple Parents)
    folder_id = models.UUIDField()
    project_id = models.UUIDField(null=True, blank=True)

    # Role Assignments (Multiple Creators)
    author_id = models.UUIDField()
    reviewer_id = models.UUIDField()

    fga_config = FGAModelConfig(
        object_type="document",

        # 🌳 MULTIPLE PARENTS
        # The document inherits permissions from BOTH the folder and the project.
        parents=[
            FGAParentConfig(
                relation="folder",
                parent_type="folder",
                local_field="folder_id"
            ),
            FGAParentConfig(
                relation="project",
                parent_type="project",
                local_field="project_id"
            )
        ],

        # 👥 MULTIPLE CREATORS
        # Both the author and the reviewer are explicitly assigned roles upon creation.
        creators=[
            FGACreatorConfig(
                relation="author",
                local_field="author_id"
            ),
            FGACreatorConfig(
                relation="reviewer",
                local_field="reviewer_id"
            )
        ]
    )
```

### 🧠 How the Mixin Handles This (Under the Hood)

Because your `FGATupleAdapter` simply iterates over these lists, if a developer saves a new `Document` with ID `100`, the mixin will flawlessly generate and queue **four distinct tuples** into the Outbox in a single transaction:

* **Parent 1:** `folder:123` is the `folder` of `document:100`
* **Parent 2:** `project:456` is the `project` of `document:100`
* **Creator 1:** `user:abc` is the `author` of `document:100`
* **Creator 2:** `user:xyz` is the `reviewer` of `document:100`


#### 1. When do these assignments happen?

The tuple assignments happen **automatically at the exact moment the Django model is saved to the database**.

When your backend executes `document.save()`, the `FGAModelSyncMixin` intercepts the save lifecycle. It looks at the `fga_config` on the model, reads the actual values stored in the `folder_id`, `project_id`, `author_id`, and `reviewer_id` fields, and calculates the required OpenFGA tuples.

Because your architecture utilizes the Transactional Outbox pattern, these tuples are written to the `FGASyncOutbox` table inside the exact same **atomic database transaction** as the Document itself. Immediately after the database commits, the Celery worker wakes up and pushes these 4 assignments to the OpenFGA server.

#### 2. On create, by which (role) user?

This requires looking at two different layers of the architecture: the **View Layer** and the **System Layer**.

##### A. The View Layer (Alice's Request)
Before the document is even created, the system must verify Alice is allowed to create it.
When Alice sends the `POST /documents/` request, your `FGAViewMixin` intercepts it. It reads Alice's identity (`user:abc`) from the Traefik middleware and asks OpenFGA: *"Does Alice have the `can_add_items` permission on `folder:123`?"*.

If OpenFGA says **yes**, the View proceeds to the creation phase.

##### B. The System Layer (The Trusted Backend)
Once the View allows the request, your Django application takes over as a "Trusted System."

OpenFGA does not actually care *who* clicked the button to create the tuples. When the Celery worker sends the batch write request to OpenFGA, it authenticates using your backend's **Store ID** and API keys. The backend dictates the new reality of the graph.

Here is exactly how your DRF ViewSet orchestrates this data flow:

```python
class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
    # ... fga_config definitions ...

    def perform_create(self, serializer):
        # 1. The Mixin already verified Alice has 'can_add_items' on the folder!

        # 2. We extract Alice's ID from the request (She is the author)
        raw_user_id = self.request.fga_user.replace("user:", "") # "abc"

        # 3. We extract Bob's ID from the JSON payload Alice submitted
        reviewer_id = self.request.data.get("reviewer_id")       # "xyz"

        # 4. We save the model. This triggers the FGAModelSyncMixin!
        serializer.save(
            author_id=raw_user_id,
            reviewer_id=reviewer_id
        )
```

##### Summary of the Flow
1. **Alice** (acting under an inherited role like `contributor` on the Folder) requests to create a document.
2. The **FGAViewMixin** verifies her permission and allows it.
3. The **ViewSet** injects Alice's ID as the `author` and Bob's ID as the `reviewer`.
4. The **FGAModelSyncMixin** saves the model and atomically queues the 4 tuple assignments (Parents and Creators) into the Outbox.
5. The **Celery Worker** acts as the trusted system and finalizes the assignments in OpenFGA.





#### 3. **"Creation Phase"** and the **"Collaboration Phase."**

When you want to add Eve as a reviewer *later*, you are no longer relying on the initial model creation. Furthermore, a single `reviewer_id` column in your PostgreSQL database can only hold one UUID. If Bob is already the reviewer, adding Eve means you either need a Many-to-Many table in Django, or you need to decouple the role from the Django model entirely.

Because you are using OpenFGA (a Zanzibar-style system), the best practice is to **decouple dynamic roles from your Django models** and write the relationship directly to the FGA graph via your API.

Here are the two architectural ways to handle adding Eve later, depending on your application's needs.

---

##### Method A: The API-Driven Approach (Recommended)
If your Django application doesn't strictly need to know *who* all the reviewers are (e.g., you rely on FGA for that data), you don't need to change your `Document` model at all.

Instead, you create a custom action on your ViewSet that allows a user (like Alice) to "invite" or "add" Eve. This beautifully leverages the `action_relations` security we just built!

```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from fga_data_sync.mixins import FGAViewMixin
from fga_data_sync.models import FGASyncOutbox
from fga_data_sync.tasks import process_fga_outbox_batch

class DocumentViewSet(FGAViewMixin, viewsets.ModelViewSet):
    # ... standard setup ...

    fga_config = FGAViewConfig(
        object_type="document",
        read_relation="can_read_document",
        # Require 'can_share' or 'owner' permission to add new reviewers
        action_relations={"add_reviewer": "can_share"}
    )

    @action(detail=True, methods=["post"])
    def add_reviewer(self, request, pk=None):
        # 1. Security Check: This automatically verifies the requester has 'can_share'
        document = self.get_object()

        # 2. Extract Eve's ID from the payload
        new_reviewer_id = request.data.get("user_id")

        # 3. Queue the tuple directly into the Outbox
        with transaction.atomic():
            FGASyncOutbox.objects.create(
                action=FGASyncOutbox.Action.WRITE,
                user_id=f"user:{new_reviewer_id}",
                relation="reviewer",
                object_id=f"document:{document.pk}"
            )
            # Trigger the worker
            transaction.on_commit(lambda: process_fga_outbox_batch.delay())

        return Response({"status": "Reviewer added successfully"}, status=status.HTTP_200_OK)
```

**Why this is great:** Your Django database stays lean. You treat OpenFGA as the absolute source of truth for "who has what role."

---

##### Method B: The Django M2M Approach (For UI Heavy Apps)
If your frontend needs to display a list of "All Reviewers" on the Document page, querying OpenFGA for that list on every page load can be inefficient. Sometimes, you need to store that data locally in PostgreSQL.

In this case, you create a related Django model and attach the `FGAModelSyncMixin` to *that* model instead of handling it inside `Document`.

```python
from django.db import models
from fga_data_sync.mixins import FGAModelSyncMixin
from fga_data_sync.structs import FGAModelConfig, FGAParentConfig

# The Core Model
class Document(FGAModelSyncMixin, models.Model):
    title = models.CharField(max_length=255)
    # ... initial creators/parents config ...

# The M2M / Role Model
class DocumentReviewer(FGAModelSyncMixin, models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    user_id = models.CharField(max_length=255) # Eve's ID

    # We configure this model to map its fields into a Document tuple!
    fga_config = FGAModelConfig(
        object_type="document",
        parents=[
            FGAParentConfig(
                relation="reviewer",       # The OpenFGA role
                parent_type="user",        # The left side of the tuple
                local_field="user_id"      # Eve's ID
            )
        ]
    )

    # 🧠 Under the hood, when you save DocumentReviewer(document_id=100, user_id="eve"):
    # It generates: user:eve is the 'reviewer' of document:100
```

**Why this is great:** When Alice wants to add Eve, she simply sends a `POST` request to create a new `DocumentReviewer` record in Django. The Mixin intercepts the save, sees that the `object_type` is actually targeting the `"document"`, and pushes the correct tuple to OpenFGA. You now have the data perfectly synced between your PostgreSQL database (for easy UI rendering) and OpenFGA (for fast authorization checks).
