# 🛡️ Configurations Reference

The `django-fga-data-sync` package utilizes strict Python `dataclasses` to define authorization rules. This ensures type safety, auto-completion in modern IDEs, and prevents misconfiguration before your app even boots.

There are two primary configuration classes you will use: `FGAModelConfig` (for database models) and `FGAViewConfig` (for API views).

---

## Configuration Defaults

::: fga_data_sync.conf.DEFAULTS
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4
!!! warning "Setting Variable Name"
    Avoiding to use `DEFAULT = ...`.

    The correct variable name in the `settings.py` is `FGA_DATA_SYNC = { ... }` !!!

## 1. View Configuration

The `FGAViewConfig` dataclass centralizes all OpenFGA authorization rules for your Django Views and ViewSets. By attaching this configuration to your view, the underlying permission classes (`IsFGAAuthorized`) and mixins (`FGAViewMixin`) automatically enforce access control.

!!! tip "The Golden Rule: Check Permissions, Not Roles"
    When configuring a view, you must only check **Permissions** (e.g., `can_read_document`, `can_update`). You should never check base Roles (e.g., `reader`, `editor`) directly. Let the OpenFGA Zanzibar graph handle the complex inheritance hierarchies for you!

::: fga_data_sync.structs.FGAViewConfig
    options:
      show_root_heading: false
      heading_level: 4
      filters:
        - "!^__post_init__$"

---

## 2. Model Configuration

The `FGAModelConfig` dataclass acts as a translation layer. It reads soft-reference identifiers (like UUIDs) from your Django Model instances and converts them into strict Zanzibar Tuples using the Transactional Outbox pattern.

!!! tip "The Golden Rule: Assign Roles, Not Permissions"
    When configuring a model's `creators` or `parents`, you must only assign base **Roles** (e.g., `owner`, `editor`). Models should never directly grant atomic permissions.

::: fga_data_sync.structs.FGAModelConfig
    options:
      show_root_heading: false
      heading_level: 4
      filters:
        - "!^__post_init__$"

::: fga_data_sync.structs.FGAParentConfig
    options:
      show_root_heading: false
      heading_level: 4
      filters:
        - "!^__post_init__$"

::: fga_data_sync.structs.FGACreatorConfig
    options:
      show_root_heading: false
      heading_level: 4
      filters:
        - "!^__post_init__$"
