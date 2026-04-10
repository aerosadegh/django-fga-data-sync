# Stateless Views & Pluggable Dashboards

In a distributed microservice architecture, your mini-apps will often need to authorize requests against external resources that they do not own.

For example, a Finance Mini-App might have a `FinanceDashboardView`. This dashboard aggregates data from local tables (like `Invoice` and `Expense`), but the authorization gate sits at the **Organization** level (e.g., *"Is this user a finance admin of the active organization?"*).

Because the Finance Mini-App does not have an `Organization` table in its local PostgreSQL database, it cannot rely on standard stateful Django models for authorization.

We solve this using **Stateless Resolution**.

---

## The Stateless Pattern (`lookup_header`)

By utilizing the `lookup_header` (or `Workspace_kwarg`) in your `FGAViewConfig`, the `IsFGAAuthorized` permission class will bypass the local database entirely. It extracts the target Object ID directly from the incoming HTTP request and queries OpenFGA.

Here is a complete example of a highly decoupled, pluggable Dashboard View.

### 1. The Dynamic Settings
To make your mini-app truly pluggable, avoid hardcoding model imports. Define the target models in your Django `settings.py` so other teams can override them if they install your app.

```python
# settings.py
FINANCE_DASHBOARD_CONFIG = {
    "INVOICE_MODEL": "finance_app.Invoice",
    "EXPENSE_MODEL": "finance_app.Expense",
}
```

### 2. The Dashboard View
Notice how this view does not import any local models at the top of the file, and relies entirely on the `HTTP_X_CONTEXT_ORG_ID` header for its OpenFGA authorization check.

```python
# views.py
from django.apps import apps
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response

from fga_data_sync.permissions import IsFGAAuthorized
from fga_data_sync.structs import FGAViewConfig

class FinanceDashboardView(APIView):
    """
    A 100% Stateless and Pluggable Dashboard.
    Authorizes via headers and loads models dynamically via settings.
    """
    permission_classes = [IsFGAAuthorized]

    # 🛡️ THE STATELESS GUARDRAIL
    # Bypasses the local DB and checks the graph directly!
    #
    # 1. Identity: "user:alice_123" (Auto-extracted by TraefikIdentityMiddleware)
    # 2. Target: "acme_corp" (Extracted from HTTP_X_CONTEXT_ORG_ID via lookup_header)
    #
    # Q: "Does `user:alice_123` have the `can_view_finance_dashboard` permission on `organization:acme_corp`?"
    fga_config = FGAViewConfig(
        object_type="organization",
        read_relation="can_view_finance_dashboard",
        lookup_header="HTTP_X_CONTEXT_ORG_ID"
    )

    def get(self, request):
        # 1. Extract the authorized Org ID from the Traefik Gateway
        org_id = request.META.get("HTTP_X_CONTEXT_ORG_ID")

        # 2. Dynamically load the configured models into memory
        dashboard_config = getattr(settings, "FINANCE_DASHBOARD_CONFIG", {})

        InvoiceModel = apps.get_model(
            dashboard_config.get("INVOICE_MODEL", "finance_app.Invoice")
        )
        ExpenseModel = apps.get_model(
            dashboard_config.get("EXPENSE_MODEL", "finance_app.Expense")
        )

        # 3. Query the dynamically loaded models!
        total_invoices = InvoiceModel.objects.filter(organization_id=org_id).count()
        total_expenses = ExpenseModel.objects.filter(organization_id=org_id).count()

        return Response({
            "dashboard_target": org_id,
            "metrics": {
                "total_invoices": total_invoices,
                "total_expenses": total_expenses
            }
        })
```

### Architectural Benefits
1. **Zero Circular Imports:** Models are loaded at runtime inside the `get()` method.
2. **Lean Databases:** You do not need to duplicate the `Organization` table across every single mini-app just to perform authorization checks.
3. **Ultimate Reusability:** Your mini-app can be installed as a third-party package by other teams, and they can point the dashboard to their own custom database tables!
