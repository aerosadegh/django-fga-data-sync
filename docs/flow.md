Howdy! Dj 5.2 Expert here.

To really lock in how beautifully this architecture works, let's look at the exact same scenario from two completely different perspectives. 

Here is the flow for the **End User** (Alice, the employee) experiencing the system, followed by the exact code the **Miniapp Developer** writes to make it happen.

http://googleusercontent.com/image_content/167



---

### 👤 1. The End-User Perspective (What Alice Experiences)

From Alice's point of view, the system is just one giant, fast, cohesive platform. She has no idea she is crossing microservice boundaries.

1. **Authentication (The Gateway):** Alice goes to your company portal and logs in. The central `dij` service verifies her password and gives her a Traefik session token.
2. **Global Role Assignment:** An HR Admin goes into the `dij` dashboard and assigns Alice as the `owner` of the "Alpha TFR". (`dij` silently writes this rule to OpenFGA).
3. **The Action (Miniapp Request):** Alice clicks a link to open the "Document Manager" Miniapp and clicks **"Create Document inside Alpha TFR"**.
4. **The Verification:** The Miniapp intercepts her click, glances at her hidden `X-User-Id` header, and instantly asks OpenFGA: *"Can Alice add documents to Alpha TFR?"* FGA says *"Yes, she's the owner."*
5. **The Result:** The document is created. Alice gets a success message in 100 milliseconds.
6. **The Background Magic:** Unbeknownst to Alice, the Miniapp's Celery worker just whispered to OpenFGA: *"Hey, Alice just created Document #99 under Alpha TFR. Make sure she is the editor."* 



---

### 💻 2. The Miniapp Developer Perspective (The Code Example)

From the Miniapp Developer's point of view, they don't care about Traefik headers, OpenFGA network latency, or Celery retry logic. They just install your `django-authz-data-sync` package and write a few lines of declarative configuration.

Here is the **complete** code a developer writes to build that exact experience for Alice:

#### Step 1: Add the Settings (`settings.py`)
```python
INSTALLED_APPS = [
    # ...
    'authz_data_sync',
    'my_mini_app',
]

MIDDLEWARE = [
    # ...
    'authz_data_sync.middleware.TraefikIdentityMiddleware', # Automatically extracts X-User-Id
]

AUTHZ_DATA_SYNC = {
    "OPENFGA_STORE_ID": "01H_YOUR_COMPANY_STORE_ID",
}
```

#### Step 2: Define the Model (`models.py`)
The developer links the Document to the folderand configures the `FGA_SETTINGS`.

```python
from django.db import models
from authz_data_sync.mixins import AuthzSyncMixin
from typing import ClassVar

class Document(AuthzSyncMixin, models.Model):
    title = models.CharField(max_length=255)
    tfr_id = models.UUIDField(db_index=True)       # Soft reference to Parent
    creator_id = models.UUIDField(db_index=True)   # Soft reference to Alice

    # The developer just defines the mapping! The Mixin handles the DB sync.
    FGA_SETTINGS: ClassVar[dict] = {
        "object_type": "document",
        "parents": [
            {"relation": "tfr", "parent_type": "tfr", "local_field": "tfr_id"}
        ],
        "creators": [
            {"relation": "editor", "local_field": "creator_id"}
        ]
    }
```

#### Step 3: Define the View (`views.py`)
The developer protects the API using the `IsFGAAuthorized` permission class we built.

```python
from rest_framework import generics
from authz_data_sync.permissions import IsFGAAuthorized
from .models import Document
from .serializers import DocumentSerializer

class DocumentCreateAPIView(generics.CreateAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    
    # 1. Turn on the FGA Security Shield
    permission_classes = [IsFGAAuthorized]
    
    # 2. Tell the shield what the rules are for Creation
    fga_create_parent_type = "tfr"
    fga_create_parent_field = "tfr_id"       # The field in the POST payload
    fga_create_relation = "contributor"      # The DSL rule: You must be a contributor to add items

    def perform_create(self, serializer):
        # 3. Save the record! (Identity middleware provides request.fga_user)
        # Strip "user:" prefix to store raw UUID in the database
        raw_user_id = self.request.fga_user.replace("user:", "")
        serializer.save(creator_id=raw_user_id)
```

**That is it.** 

With those three files, your miniapp developers have implemented an enterprise-grade, perfectly synced, globally distributed authorization model. They get to focus 100% on writing business logic while your package handles the heavy lifting!