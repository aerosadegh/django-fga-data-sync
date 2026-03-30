# Django Authz Data Sync 🤠

Welcome to the ultimate enterprise authorization platform.

A declarative, Outbox-pattern OpenFGA synchronizer for Django models. This package automatically translates your Django relational models into OpenFGA authorization graph tuples. It guarantees perfect synchronization between your local PostgreSQL database and your distributed OpenFGA server using the Transactional Outbox pattern and Celery.

## Why this package?
* **Zero-Boilerplate Synchronization:** Write standard Django models, and we handle the distributed FGA writes.
* **Declarative Security:** Secure your DRF endpoints using simple dictionary configurations.
* **100% Decoupled:** Change business security rules without deploying new Python code.

Head over to the **Getting Started** section to wire it up!