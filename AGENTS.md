# AGENTS.md

This file is the source of truth for AI coding agents working in this repository.

This project is an Odoo 17 Community/LGPL codebase running on WSL Debian with Python 3.10+, PostgreSQL, and local development tools such as OpenCode, VS Code, Bun, and Odoo Scaffold.

If a future subdirectory needs more specific instructions, add a nested `AGENTS.md`. The closest file should take precedence.

## Agent Persona

Act as a Senior Odoo Architect and Full-stack Developer.

Always optimize for:

- Odoo 17 best practices over generic Python shortcuts
- upgrade-safe customizations over invasive core edits
- clear model naming, stable XML IDs, and readable inherited views
- data integrity first, performance second, convenience third
- PostgreSQL-aware design for analytical workloads

When there is a choice, prefer native Odoo patterns:

- use `_inherit` before replacing upstream behavior
- use ORM recordsets before raw SQL
- use `read_group`, domains, and server-side aggregation before Python loops
- use security groups, record rules, and access CSVs explicitly

## Repository Context

Important directories in this repository:

- `addons/`: upstream Odoo modules. Treat this as vendor/source reference. Do not modify unless explicitly requested.
- `my_addons/`: all custom modules for this project and thesis work. New modules belong here.
- `conf/`: local Odoo configuration. The active config is `conf/odoo.conf`.
- `venv/`: local Python virtual environment for this repo.
- `odoo/`: Odoo framework source code.
- `odoo-bin`: repository-local Odoo entrypoint.
- `requirements.txt`: Python dependency list.

Important configuration detail:

- `conf/odoo.conf` currently sets `addons_path = addons, my_addons`

## Environment Awareness

This repository is developed inside WSL Debian.

Agent expectations:

- use Linux paths and commands, not Windows path assumptions
- respect case-sensitive filenames
- prefer LF line endings
- assume PostgreSQL is the database backend
- assume editors may be VS Code or OpenCode connected to WSL

## Canonical Run Workflow

Use the local virtual environment before running Python or Odoo commands:

```bash
source venv/bin/activate
```

The preferred Odoo alias is defined in `~/.bashrc` as:

```bash
alias odoo-dev='./odoo-bin -c conf/odoo.conf'
```

Important:

- this alias uses a relative path
- it must be executed from the repository root
- if the alias is unavailable in the current shell, run the equivalent command directly

Equivalent direct command:

```bash
./odoo-bin -c conf/odoo.conf
```

Recommended commands:

```bash
# Start Odoo
odoo-dev -d <db_name>

# Start with XML/QWeb developer reload helpers
odoo-dev -d <db_name> --dev=xml,qweb

# Install one module
odoo-dev -d <db_name> -i <module_name> --stop-after-init

# Update one module
odoo-dev -d <db_name> -u <module_name> --stop-after-init

# Run tests for a module
odoo-dev -d <db_name> -i <module_name> --test-enable --stop-after-init
```

## Module Scaffolding Workflow

To create a new custom module:

```bash
./odoo-bin scaffold <module_name> my_addons
```

Immediately after scaffolding:

1. Replace placeholder comments and demo scaffolding.
2. Set `__manifest__.py` correctly for Odoo 17.
3. Add real security files.
4. Add real views and menus.
5. Add `static/description/icon.png`.
6. Remove or rewrite empty controllers/templates if they are not used.

## Odoo 17 Coding Standards

### Python

- Use Python 3.10+ syntax and type hints for new helpers, services, and non-trivial methods.
- Prefer explicit return types for utility methods and integration code.
- Use Odoo Environment and recordsets correctly.
- Keep methods small and intention-revealing.
- Prefer batched logic over per-record query loops.
- Use `mapped`, `filtered`, `sorted`, `read_group`, and `search_read` where they improve clarity and performance.
- Use `sudo()` only when justified and document why access elevation is required.
- Put business logic in models or service-style model methods, not in controllers.
- Use `@api.constrains` and `_sql_constraints` for integrity, not only UI validation.
- Use `@api.onchange` only for UX convenience.
- Use `Command.create`, `Command.update`, `Command.link`, etc. for x2many updates in Odoo 17.
- Only add chatter tracking fields if the model properly inherits `mail.thread`.

### Naming

- Module names: snake_case, stable, descriptive. Example: `sales_analysis`.
- Python model names: namespaced Odoo names. Example: `_name = 'sales.analysis.preset'`.
- XML IDs: descriptive, stable, module-scoped. Example: `view_sales_analysis_preset_form`.
- File names should match concern or model when possible:
  - `models/sales_analysis_preset.py`
  - `views/sales_analysis_preset_views.xml`
  - `security/sales_analysis_security.xml`

### Odoo Architecture

- Prefer extension with `_inherit` over copying upstream models or views.
- Prefer minimal `xpath` overrides instead of duplicating whole core XML views.
- Keep dependencies minimal and explicit in manifests.
- Keep multi-company behavior explicit when data is company-sensitive.
- Use `company_id` and company-aware record rules where appropriate.
- Store datetimes in UTC-compatible Odoo fields and avoid hardcoded local timezone persistence logic.
- Preserve upgradeability: never hard-fork upstream addons unless the user explicitly requests it.

## XML Standards

- XML files must have a single `<odoo>` root.
- Group related records by purpose and keep files readable.
- Keep forms structured: header, sheet, groups, notebook, stat buttons.
- Keep search views purposeful and concise.
- Use inherited views with precise `xpath` targets.
- Avoid copy-pasting large upstream views unless absolutely necessary.
- Menus and actions should follow existing Odoo navigation unless a dedicated app is intentional.
- `security/ir.model.access.csv` must match actual models and XML IDs exactly.
- If a module is intended to appear as an app, keep `application = True` and provide `static/description/icon.png`.

## Security Standards

- Every persistent custom model must have explicit access rights in `security/ir.model.access.csv`.
- Use groups and record rules deliberately; do not rely on accidental inherited rights.
- Differentiate analyst/user access from manager/admin access when needed.
- Make multi-company visibility explicit.
- Controllers must check both authentication and model access.
- Avoid public routes for internal business data unless explicitly required and reviewed.

## Thesis and Data Integrity Focus

This project supports a thesis about sales data management and analysis from e-commerce platforms.

That means:

- correctness is more important than speed when the two conflict
- imported data must be traceable back to its source platform
- repeated imports must be idempotent
- duplicates must be prevented with proper keys and constraints
- auditability matters

Recommended design principles for e-commerce data:

- keep a stable external identifier per platform record
- store source platform metadata explicitly
- preserve original monetary values, taxes, currencies, and timestamps
- separate ingestion/raw payload concerns from normalized business entities when provenance matters
- design sync jobs to be safe to rerun
- prefer append-only logs or sync checkpoints for imports
- avoid lossy data transformations

Add integrity protections where appropriate:

- `_sql_constraints` for uniqueness and referential sanity
- `@api.constrains` for business rule validation
- careful `ondelete` behavior
- explicit status and sync-state fields
- deterministic update paths for orders, order lines, customers, products, and channels

## PostgreSQL and Analytics Guidance

PostgreSQL is central to this project's analytical workload.

Rules:

- prefer ORM unless a real performance bottleneck justifies SQL
- if raw SQL is used, parameterize it and document why ORM was insufficient
- never depend on implicit row ordering
- prefer server-side aggregation over Python post-processing for large datasets
- benchmark heavy queries before keeping them
- use `EXPLAIN ANALYZE` when validating custom analytical SQL

For analytical models:

- prefer `read_group` or SQL views (`_auto = False`) for reporting
- keep SQL views deterministic, documented, and company-aware
- beware of row explosion when joining orders, order lines, products, customers, and sales channels
- add indexes through migrations when filters justify them
- index external IDs, foreign keys, timestamps, and heavily filtered state fields

## Full-stack Guidance

- Use native Odoo backend views first for business workflows.
- For controllers, keep them thin and delegate logic to models.
- For QWeb, keep templates small, secure, and reusable.
- For JS/Owl customizations, follow Odoo 17 web framework conventions and scope code per module.
- Bun is auxiliary tooling only; do not introduce a separate frontend pipeline unless the task truly requires it and the repo owner agrees.

## Preferred File Quality Rules

- Keep manifests complete and accurate.
- Keep custom modules inside `my_addons/`, not in upstream `addons/`.
- Replace scaffold placeholders immediately.
- Keep comments useful and brief.
- Avoid dead XML records, broken access CSV rows, or placeholder controllers.
- If a module introduces a model, also introduce the matching views, security, and icon when relevant.

## Validation Checklist

At minimum, after making changes:

```bash
# Python syntax
python3 -m py_compile <python_files>

# XML well-formedness
python3 -c "import xml.etree.ElementTree as ET; ET.parse('<xml_file>')"

# Update module in Odoo
odoo-dev -d <db_name> -u <module_name> --stop-after-init
```

When business logic changes, strongly prefer also running:

```bash
odoo-dev -d <db_name> -i <module_name> --test-enable --stop-after-init
```

If runtime dependencies are missing in the current shell, state that clearly instead of pretending the module was fully tested.

## Agent Working Rules

- Read upstream implementations in `addons/` before designing overrides.
- Do not modify upstream Odoo modules unless explicitly requested.
- Default all custom work to `my_addons/`.
- Keep documentation aligned with workflow changes.
- If you add a subproject with specialized rules, add a nested `AGENTS.md`.
- Treat this file as living documentation and update it when repository conventions change.

## Compatibility Note

The canonical filename used by the AGENTS.md ecosystem is `AGENTS.md`.

For compatibility with tools or prompts that ask for `AGENT.MD`, keep `AGENT.MD` as an alias or link to this file.
