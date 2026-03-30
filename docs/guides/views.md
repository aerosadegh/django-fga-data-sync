# Securing API Views

The developer protects the API using the `IsFGAAuthorized` permission class we built.

You do not have to write custom logic to parse identity headers. The `TraefikIdentityMiddleware` automatically extracts `X-User-Id`.

### Example: Securing a Creation Endpoint

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
    fga_create_parent_type = "folder"     
    fga_create_parent_field = "folder_id"    # The field in the POST payload
    fga_create_relation = "contributor"      # The DSL rule: You must be a contributor to add items

    def perform_create(self, serializer):
        # 3. Save the record! (Identity middleware provides request.fga_user)
        # Strip "user:" prefix to store raw UUID in the database
        raw_user_id = self.request.fga_user.replace("user:", "")         
        serializer.save(creator_id=raw_user_id) 
```

For ViewSet we have this also

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from authz_data_sync.permissions import IsFGAAuthorized
from .models import Document

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    permission_classes = [IsFGAAuthorized]
    
    # Standard CRUD Permissions
    fga_object_type = "document"
    fga_read_relation = "can_read"
    fga_update_relation = "can_update"
    fga_delete_relation = "can_delete"
    
    # Map specific ViewSet actions to FGA permissions!
    fga_action_relations = {
        "comment": "can_create_comment" # Matches the function name below
    }

    @action(detail=True, methods=['patch'])
    def comment(self, request, pk=None):
        # 🛡️ Because of the dictionary above, IsFGAAuthorized already 
        # verified the user has the 'can_create_comment' permission!
        document = self.get_object()
        # ... logic to save the comment ...
        return Response({"status": "Comment added!"})
```
