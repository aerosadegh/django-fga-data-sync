# 🏗️ Project Architecture & Philosophy: Django FGA Data Sync

This document outlines the core philosophy behind the `django-fga-data-sync` package, why it was created, and the architectural patterns it leverages to provide enterprise-grade authorization for Django developers.

## 1. Why We Built This Project

In a standard Django application, authorization logic (checking if a user can read, edit, or delete an object) is often scattered across views, serializers, and custom permission classes. This creates a tightly coupled system where changing a security rule requires rewriting and deploying Python code.

Furthermore, as systems scale into microservices, relying solely on the Django ORM for permissions becomes impossible.

We built `django-fga-data-sync` to solve these problems by adopting the **Google Zanzibar** model via **OpenFGA**. The core philosophy is **100% Decoupling**: your application should not evaluate permissions; it should merely ask a dedicated authorization engine for the answer.

## 2. The Core Architectural Patterns

To make this decoupling seamless and reliable, the package implements several advanced architectural patterns under the hood.

### The Transactional Outbox Pattern
A major challenge in distributed systems is "Dual Writes"—saving data to your local PostgreSQL database and simultaneously sending an HTTP request to an external service (like OpenFGA). If the network fails, your database and OpenFGA become out of sync.

This package solves this using the **Transactional Outbox Pattern**:
1. When a Django model is saved or deleted, the `FGAModelSyncMixin` intercepts the action.
2. Instead of calling OpenFGA directly, it generates the necessary relationship tuples (e.g., "user:bob is the owner of folder:123") and saves them to a local `FGASyncOutbox` table within the same atomic database transaction.
3. Once the database commit is successful, a Celery task (`process_fga_outbox_batch`) is triggered to asynchronously sweep the outbox and push the tuples to the OpenFGA server.

This guarantees **eventual consistency**. If the OpenFGA server goes down, the Celery task will utilize exponential backoff to retry the batch later.
### Declarative Security
The package embraces a declarative approach. Developers do not write complex logic to sync data or check permissions. Instead, they define strict, type-safe dataclass configurations (`FGAModelConfig` on models or `FGAViewConfig` on views), and the underlying mixins handle the complex graph traversals and API calls.

## 3. Developer Capabilities (What this enables)

By installing this package, developers gain access to a suite of highly abstracted, powerful capabilities:

* **Zero-Boilerplate Synchronization:** By simply adding the `FGAModelSyncMixin` to a model and defining the `fga_config` attribute with the `FGAModelConfig` dataclass, the package automatically calculates tuple diffs on every `save()` or `delete()` and syncs them to OpenFGA.
* **Automatic Identity Extraction:** The `TraefikIdentityMiddleware` automatically intercepts internal traffic from your gateway, dynamically maps incoming headers (like `X-User-Id` or `X-Context-Org-Id`) based on your settings, and attaches formatted FGA context strings (e.g., `user:123`) to the request lifecycle without any hardcoded constraints.
* **Plug-and-Play Endpoint Protection:** Developers can secure DRF views instantly using the `IsFGAAuthorized` permission class. It automatically reads the `fga_config` attribute (an instance of `FGAViewConfig`) to verify access before a view executes. It even supports custom ViewSet actions mapping via the `action_relations` dictionary within that configuration.
* **Parent Cascading Validation:** When creating new objects via POST requests, the framework automatically verifies if the user holds the required role on the *parent* object (using `create_parent_type` and `create_relation` defined in your `FGAViewConfig`) before allowing the creation.
* **Secure Queryset Filtering:** The `FGAViewMixin` (and related mixins) automatically intercepts standard DRF list views. It asks OpenFGA for an array of allowed IDs and injects an `id__in` filter into the Django ORM queryset, ensuring users never see objects they don't have access to.
