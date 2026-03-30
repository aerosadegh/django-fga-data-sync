# 🏗️ Designing the OpenFGA Schema (DSL)

To get the most out of `django-authz-data-sync`, your OpenFGA schema must follow the **Roles vs. Permissions Pattern**. 

This is an industry-standard Zanzibar architecture that completely decouples your application's security logic from your Python code. By strictly separating *who a user is* from *what a user can do*, you can change business rules on the fly without ever deploying new Django code.

## 1. The Core Philosophy

Every `type` in your OpenFGA DSL should be split into three distinct sections:
1. **Structural Links:** How does this object relate to its parent?
2. **Roles (The "Who"):** The titles users hold (`owner`, `editor`, `reader`). These are assigned by your Django **Models**.
3. **Permissions (The "What"):** The actions users can take (`can_read`, `can_update`, `can_delete`). These are checked by your Django **Views**.

## 2. Example Schema Architecture

Here is the standard schema design for our cascading hierarchy (`Organization` -> `Direcory` -> `D_OBJ`).

```dsl
model
  schema 1.1

type user

# ==========================================
# LEVEL 1: ORGANIZATION
# ==========================================
type organization
  relations
    # 1. Roles
    define admin: [user]
    define manager: [user] or admin
    
    # 2. Permissions
    define can_manage_settings: admin
    define can_view_dashboard: manager

# ==========================================
# LEVEL 2: folder(Child of Organization)
# ==========================================
type tfr
  relations
    # 1. Structural Link
    define organization: [organization]

    # 2. Roles (Inheriting from Parent!)
    define owner: [user] or admin from organization
    define contributor: [user] or manager from organization or owner
    
    # 3. Permissions
    define can_edit_tfr: owner
    define can_add_items: contributor

# ==========================================
# LEVEL 3: D_OBJ (Child of TFR)
# ==========================================
type d_obj
  relations
    # 1. Structural Link
    define tfr: [tfr]

    # 2. Roles (Inheriting from Parent!)
    define editor: [user] or owner from tfr
    define reader: [user] or contributor from folderor editor
    
    # 3. Permissions
    define can_read: reader
    define can_update: editor
    define can_delete: editor
```

## 3. How to Map Your Django Code to the DSL

Your miniapp developers must follow this strict mapping rule to ensure maximum scalability:

### Rule 1: Models only assign ROLES.
When configuring a Django Model's `FGA_SETTINGS`, the `creators` list must only assign base **Roles** (like `editor` or `owner`). Models should never directly assign permissions.

```python
# ❌ BAD: Assigning a permission directly
"creators": [{"relation": "can_update", "local_field": "creator_id"}]

# ✅ GOOD: Assigning a role
"creators": [{"relation": "editor", "local_field": "creator_id"}]
```

### Rule 2: Views only check PERMISSIONS.
When configuring a DRF View's `FGA_VIEW_SETTINGS`, the configuration must only check **Permissions** (like `can_read` or `can_update`). Views should never check roles.

```python
# ❌ BAD: Checking a role directly
FGA_VIEW_SETTINGS = {
    "list_relation": "reader",
    "detail_relations": {"PUT": "editor"}
}

# ✅ GOOD: Checking a permission
FGA_VIEW_SETTINGS = {
    "list_relation": "can_read",
    "detail_relations": {"PUT": "can_update"}
}
```

## 4. Why Do We Do This? (The Zero-Code Update)

By adhering to this pattern, you gain **Zero-Code Updates**.

Imagine your product requirements change: *"Going forward, only folderOwners can update a D_OBJ. Explicit Editors are no longer allowed."*

Because your Django view is strictly checking `"can_update"`, you do not need to touch your Python code, write new unit tests, or redeploy your microservice. You simply update the OpenFGA DSL:

```dsl
# OLD:
# define can_update: editor

# NEW:
define can_update: owner from tfr
```
The moment the new schema is saved to OpenFGA, your Django views will automatically start enforcing the new rule.

