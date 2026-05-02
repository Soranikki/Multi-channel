# Dev Log — Multichannel Sales ERP (Thesis Project)

This file tracks every file created or modified per phase, what it does, and the
install/test result for each phase. Use this for system review after completion.

---

## Phase 1 — Data Foundation
**Goal:** Core models, views, security, and menus. No pipeline logic yet.
**Status:** ✅ Complete — module installs cleanly, 4 DB tables created, seed channels verified in DB.

### Module: `my_addons/multichannel_sync/`

| File | Role |
|---|---|
| `__manifest__.py` | Module manifest. Declares name, version, `depends: ['base', 'mail']`, `application: True`. References all security, data, and view files in correct load order. |
| `__init__.py` | Package entry point. Imports the `models` package only (controllers deferred to later phases). |
| `models/__init__.py` | Imports all 4 model modules: `mc_channel`, `mc_product`, `mc_product_mapping`, `mc_sync_log`. |
| `models/mc_channel.py` | **Channel model** (`mc.channel`). Represents a sales platform (Shopee, TikTok Shop, Manual). Fields: `name`, `code` (selection), `active`, `sequence`, `last_sync_at`, `sync_status`. Computed stat counters: `mapping_count`, `raw_order_count`, `order_count`. Button action: `action_open_mappings()` opens product mappings filtered to this channel. |
| `models/mc_product.py` | **Internal Product model** (`mc.product`) — the Single Source of Truth for all products. Fields: `name`, `internal_sku` (unique), `description`, `category`, `sale_price`, `cost_price`, `active`, `image`. Inventory fields: `stock_qty`, `reserved_qty`, `available_qty` (computed: stock − reserved), `low_stock_threshold`, `is_low_stock` (computed). `@api.constrains` prevents negative stock. Button action: `action_open_mappings()`. |
| `models/mc_product_mapping.py` | **Product Mapping model** (`mc.product.mapping`). Maps one external platform SKU per channel to one internal product. Fields: `channel_id`, `product_id`, `external_sku`, `external_name`, `is_active`. SQL unique constraint: `(channel_id, external_sku)` — prevents ambiguous mapping during pipeline processing. Related convenience fields: `internal_sku`, `product_name`, `channel_code`. |
| `models/mc_sync_log.py` | **Sync Log model** (`mc.sync.log`). Append-only audit log for pipeline events. Fields: `channel_id`, `log_type` (info/warning/error), `message`, `reference` (external order ID), `timestamp`. Class method `_log()` used by other models to write entries without boilerplate. |
| `security/multichannel_security.xml` | Defines module category and two security groups: `group_mc_user` (standard operator — read channels, full CRUD on products/mappings/logs) and `group_mc_manager` (full access to all models including channel write). Record rules: users read all channels; managers write all channels. |
| `security/ir.model.access.csv` | Explicit ACL rows for all 4 models × 2 groups. Users cannot delete products or write channels. Managers have full CRUD everywhere. |
| `data/mc_channel_data.xml` | Seed data (`noupdate=1`). Pre-loads two channels on install: **Shopee** (code=shopee, color=1) and **TikTok Shop** (code=tiktok, color=4). Safe to edit after install without being overwritten on module update. |
| `views/mc_channel_views.xml` | Views for `mc.channel`: search (name, code, status filters + group-by), tree (sequence handle, name, code, sync status badge, last sync, mapping count), form (stat button → mappings, config group, sync status group, description). Window action `action_mc_channel` (tree+form). |
| `views/mc_product_views.xml` | Views for `mc.product`: search (name, SKU, category, low-stock filter), tree (SKU, name, category, price, stock/reserved/available qty, low-stock threshold — red row on low stock), kanban (stock alert badge, available qty), form (image avatar, stat button → mappings, identification/pricing groups, inventory tab with stock levels + alert threshold, description tab). Window action `action_mc_product` (tree+kanban+form). |
| `views/mc_product_mapping_views.xml` | Views for `mc.product.mapping`: search (external SKU, name, product, channel filters; grouped by channel by default), editable tree (channel, external SKU, external name, internal product, internal SKU readonly, active toggle), form (channel + mapping groups, external platform group). Window action `action_mc_product_mapping` (tree+form). |
| `views/mc_sync_log_views.xml` | Views for `mc.sync.log`: search (message, reference, channel, type filters, today filter, group-by date/channel/type), read-only tree (timestamp, type badge, channel, reference, message — red rows on error, orange on warning). Two window actions: `action_mc_sync_log` (all logs) and `action_mc_sync_log_errors` (pre-filtered to errors). |
| `views/menus.xml` | App menu "Multichannel Sales" (sequence=40, top-level app icon). Sub-menus: **Product Catalog** → Products, Channel Mappings; **Logs** → All Sync Logs, Error Log; **Configuration** (manager only) → Sales Channels. |
| `static/description/icon.png` | App icon displayed in the Odoo home screen app list. |

---

<!-- Phase 2 will be appended here -->

## Phase 2 — Raw Data Ingestion & Parsing
**Goal:** Receive mock platform payloads, parse them into structured data, and handle errors cleanly.
**Status:** ✅ Complete — module updates cleanly, `mc_raw_order` table created, Shopee and TikTok parsers implemented and schema-validated.

### Module: `my_addons/multichannel_sync/` — files added or changed

| File | Role |
|---|---|
| `models/payload_schemas.py` | **Payload Schema Definitions** (new). Documents and constants for both platform JSON formats. Shopee v2 format: `order_sn`, `item_list[].item_sku`, `recipient_address`, `create_time` (Unix int). TikTok Open API format: `order_id`, `line_items[].seller_sku`, `recipient_address`, `payment.total_amount`, `create_time` (ISO string). All field name constants are imported by the parser to avoid magic strings. |
| `models/mc_raw_order.py` | **Raw Order model** (`mc.raw.order`) (new). Stores one unprocessed JSON payload per incoming platform order. State machine: `new → parsed → processed → error`. Fields: `channel_id`, `external_order_id`, `raw_payload` (immutable), `state`, `error_message`, `received_at`, `parsed_at`, `processed_at`. Parsed intermediate fields: `parsed_customer_name`, `parsed_customer_phone`, `parsed_shipping_address`, `parsed_order_date`, `parsed_total_amount`, `parsed_currency`, `parsed_items_json`. Link to resulting order: `order_id`. SQL unique constraint: `(channel_id, external_order_id)` prevents duplicate ingestion. Inherits `mail.thread` for chatter/audit trail. Parser dispatch: `_parse_raw_order()` → `_parse_shopee()` or `_parse_tiktok()` based on `channel_id.code`. Each parser validates required fields and raises `ValueError` with a clear message on failure. Timestamp helpers: Shopee Unix int → UTC datetime, TikTok ISO string → datetime. On error: sets `state='error'`, writes `error_message`, creates a `mc.sync.log` entry. UI actions: `action_parse()` (single record), `action_open_order()` (navigate to resulting mc.order). |
| `models/__init__.py` | Updated to import `mc_raw_order` (and `payload_schemas` is imported by `mc_raw_order` directly). |
| `views/mc_raw_order_views.xml` | **Raw Order views** (new). Search view: state filters (New/Parsed/Processed/Error), channel filter, today filter, group-by channel/state/date. Tree view: color-coded rows (red=error, green=processed, blue=parsed, grey=new), columns: received_at, channel, external order ID, state badge, customer, amount, currency, parsed_at, processed_at. Form view: header Parse button (visible only on new/error), statusbar showing state progression, stat button → resulting order (visible once processed), source group + parsed customer info group, red alert box on error with error_message, Raw Payload tab (plain text), Parsed Items tab, chatter. Two window actions: `action_mc_raw_order` (all orders grouped by channel) and `action_mc_raw_order_errors` (pre-filtered errors). Server action `action_mc_raw_order_parse_all` bound to list view Action menu — triggers `action_parse_all_new()`. |
| `security/ir.model.access.csv` | Updated — added ACL rows for `mc.raw.order`: users can read/write/create (not delete); managers have full CRUD. |
| `views/menus.xml` | Updated — added **Orders** section (sequence=30) with sub-menus: Raw Orders, Raw Order Errors. |
| `__manifest__.py` | Updated — added `views/mc_raw_order_views.xml` to data load list. |

---

<!-- Phase 3 will be appended here -->

## Phase 2 (Refactor) — Standard Payload Contract
**Status:** ✅ Refactored — platform-specific parsers removed. Odoo now speaks only the standard contract defined by the Integration Service.

### Architectural decision recorded:
The external Integration Service (FastAPI) handles all platform-specific normalization.
Odoo receives one standard JSON format regardless of source channel.
Adding a new channel (Lazada, Temu, etc.) requires zero changes inside Odoo.

### Files changed:
| File | Change |
|---|---|
| `models/payload_schemas.py` | **Deleted** — Shopee/TikTok field name constants removed entirely. |
| `models/mc_raw_order.py` | **Rewritten** — `_parse_shopee()` and `_parse_tiktok()` replaced by single `_extract_standard_payload()`. Validates standard contract: `external_order_id`, `items[]` (required), plus optional `order_date`, `customer_*`, `shipping_address`, `currency`, `total_amount`. Contract documented at top of file. |
| `controllers/controllers.py` | **New** — HTTP controller `POST /api/mc/raw-order`. FastAPI calls this to push a normalized payload into Odoo. Performs API key auth, resolves `channel_code` to `mc.channel`, stores raw payload, returns `{raw_order_id}`. Handles duplicate (409) and missing channel (400) cleanly. |
| `__init__.py` | Updated — `controllers` package re-enabled now that the controller is real code. |

---

## Phase 3 — Order Processing Pipeline
**Goal:** Transform standardized JSON payloads (received from the Integration Service) into relational ERP records: resolve external SKUs to internal products via mc.product.mapping, create mc.order + mc.order.line records, and trigger stock reservation — all within Odoo's business logic layer.
**Status:** ✅ Complete — 8 DB tables created, sequence installed, module updates cleanly.

### Module: `my_addons/multichannel_sync/` — files added or changed

| File | Role |
|---|---|
| `models/mc_order.py` | **Order model** (`mc.order`) and **Order Line model** (`mc.order.line`) (new). `mc.order`: sequence-generated name (`ORD/YYYY/NNNNN`), channel, external_order_id, raw_order_id (link back), customer fields, order_date, state machine (`draft→confirmed→done/cancelled`), total_amount (computed from lines), chatter tracking. State actions: `action_confirm()` — calls `_check_stock_availability()` then `_deduct_stock()`; `action_mark_done()`; `action_cancel()` — restores or releases stock depending on current state. Pipeline entry: `_create_from_raw(raw_order)` classmethod — resolves all external SKUs via `mc.product.mapping`, fails fast if ANY SKU is unmapped (no partial orders), creates order + lines, reserves stock. SQL unique constraint: `(channel_id, external_order_id)` — idempotency guarantee. `mc.order.line`: product_id, mapping_id (which mapping resolved it), external_sku (platform traceability), quantity, unit_price, discount, subtotal (computed). |
| `models/mc_stock_move.py` | **Stock Move model** (`mc.stock.move`) (new). Append-only inventory audit log. Fields: product_id, move_type (in/out/adjustment), quantity, signed_quantity (computed: negative for out), reference (order name), channel_id, note, move_date. Never created manually — always written by order confirmation/cancellation logic. |
| `models/mc_raw_order.py` | Updated — added `_process_raw_order()` method: calls `mc.order._create_from_raw()`, sets state to `processed`, links `order_id`, logs success. On failure: sets state to `error`, logs to `mc.sync.log`. Added `action_process()` (single record button) and `action_process_all_parsed()` (batch list action). |
| `models/mc_channel.py` | Updated — added `action_run_pipeline()`: step 1 parses all `new` raw orders for this channel, step 2 processes all `parsed` raw orders, updates `last_sync_at` and `sync_status` on the channel record. |
| `models/__init__.py` | Updated — imports `mc_stock_move` and `mc_order` (in correct dependency order before `mc_raw_order`). |
| `data/mc_sequence_data.xml` | New — IR sequence for `mc.order`: prefix `ORD/%(year)s/`, 5-digit padding (`ORD/2026/00001`). `noupdate=1`. |
| `views/mc_order_views.xml` | New — Views for `mc.order`: search (name, external ID, customer, channel, state filters, group-by channel/state/month), tree (color-coded by state: blue=draft, orange=confirmed, green=done, muted=cancelled, monetary total), form (header workflow buttons: Confirm/Mark Done/Cancel, statusbar, stat button → raw order, order info + customer groups, editable order lines tab with subtotal, notes tab, chatter). Window action `action_mc_order`. Server action `action_mc_raw_order_process_all` bound to raw order list view Action menu. |
| `views/mc_stock_move_views.xml` | New — Views for `mc.stock.move`: search (product, reference, channel, type filters, today filter, group-by product/channel/type/date), read-only tree (color-coded: green=in, red=out, blue=adjustment). Window action `action_mc_stock_move`. |
| `views/mc_channel_views.xml` | Updated — added "Run Pipeline" button in form header (manager only, with confirmation dialog). |
| `views/menus.xml` | Updated — added **Orders** sub-menu (All Orders, Raw Orders, Raw Order Errors) and **Inventory** sub-menu (Stock Movements). |
| `security/ir.model.access.csv` | Updated — added ACL rows for `mc.order` (users: read+write, no create/delete), `mc.order.line` (users: read+write), `mc.stock.move` (users: read only, managers: full CRUD). |
| `__manifest__.py` | Updated — added `data/mc_sequence_data.xml`, `views/mc_order_views.xml`, `views/mc_stock_move_views.xml`. |

---

<!-- Phase 4 will be appended here -->

## Phase 4 — Inventory Management & Business Logic
**Goal:** Stock levels are tracked, deducted on order confirmation, and protected against overselling. Manual adjustments and dedicated inventory monitoring are available.
**Status:** ✅ Complete — module updates cleanly, wizard table created, all views load.

### Notes on pre-built items (4.1–4.6)
Tasks 4.1 through 4.6 were implemented ahead of schedule as part of the Phase 3 pipeline build:
- **4.1** — `stock_qty`, `reserved_qty`, `available_qty`, `low_stock_threshold`, `is_low_stock` fields on `mc.product` ✅
- **4.2** — `mc.stock.move` model + list view ✅
- **4.3** — `action_confirm()` + `_deduct_stock()` on `mc.order` ✅
- **4.4** — `_check_stock_availability()` — overselling prevention ✅
- **4.5** — `action_cancel()` + `_restore_stock()` + `_release_reservation()` ✅
- **4.6** — Stock reservation on `_create_from_raw()` draft creation ✅

### Module: `my_addons/multichannel_sync/` — files added or changed

| File | Role |
|---|---|
| `models/mc_stock_adjustment_wizard.py` | **Stock Adjustment Wizard** (`mc.stock.adjustment.wizard`, TransientModel) (new). Simple wizard to add or remove stock from a product with a required reason. Fields: `product_id` (readonly), `current_stock` (readonly, shown for reference), `adjustment_type` (add/remove radio), `quantity`, `reason`. `action_apply()`: validates quantity > 0, blocks removal that would make stock negative, writes `product.stock_qty`, creates `mc.stock.move` (type=adjustment, quantity positive for add, negative for remove), closes dialog. |
| `models/mc_product.py` | Updated — added `stock_move_count` and `pending_order_count` stat counter fields (computed, non-stored). Added `_compute_stock_move_count()` (counts `mc.stock.move` for this product), `_compute_pending_order_count()` (counts `mc.order.line` where `order_id.state = draft`). Added `action_open_stock_moves()` (opens filtered stock move list), `action_open_pending_orders()` (opens draft orders containing this product), `action_adjust_stock()` (opens adjustment wizard as a dialog with `default_product_id` context). |
| `models/__init__.py` | Updated — imports `mc_stock_adjustment_wizard`. |
| `views/mc_stock_adjustment_wizard_views.xml` | New — Wizard form view with product/current stock group and adjustment/quantity/reason group. Footer: "Apply Adjustment" (primary) and "Cancel". Window action `action_mc_stock_adjustment_wizard` (target=new). |
| `views/mc_product_views.xml` | Updated — added two new stat buttons to `button_box`: **Stock Moves** (`fa-exchange`, count + `action_open_stock_moves`) and **Pending Orders** (`fa-shopping-cart`, count + `action_open_pending_orders`). Added **Adjust Stock** button inside the Inventory tab (opens wizard). |
| `views/mc_inventory_monitor_views.xml` | New — Dedicated inventory monitoring list view (`mc.product.inventory.monitor.tree`). Sorted by `available_qty` ascending (most critical first). Red rows on `is_low_stock`, muted on inactive. Columns: SKU, name, category, on-hand, reserved, available, alert threshold, low stock flag. Window action `action_mc_inventory_monitor` with `search_default_low_stock: 1` context so Low Stock filter is pre-applied on open. |
| `views/menus.xml` | Updated — added **Inventory Monitor** sub-menu under Inventory (sequence=20), pointing to `action_mc_inventory_monitor`. |
| `security/ir.model.access.csv` | Updated — added ACL rows for `mc.stock.adjustment.wizard`: users and managers both get full CRUD (required for transient wizard). |
| `__manifest__.py` | Updated — added `views/mc_stock_adjustment_wizard_views.xml` and `views/mc_inventory_monitor_views.xml` to data load list. |

---

<!-- Phase 5 will be appended here -->

## Phase 5 — Product Hybrid, Refactor & Analytics
**Goal:** Improve all existing models (Product, Channel, Order pipeline, Inventory), add optional Odoo product.template link, build Dashboard analytics, and expose outbound API routes for the Integration Service.
**Status:** ✅ Complete — module installs cleanly (928 queries), SQL view `mc_analysis_report` created, all new API routes active.

### Architectural decisions recorded:
- `mc.product` keeps its own stock/price fields (SSOT for this system) but gains an **optional Many2one to `product.template`** for Odoo catalog linkage. No `_inherits` — stay in full control.
- Dashboard analytics live **inside `multichannel_sync`** (no separate module needed). `mc.analysis.report` is a SQL view (_auto=False) joining `mc_order + mc_order_line + mc_product + mc_channel`.
- Integration Service URL and API key both moved from `odoo.conf` hardcoding to **`ir.config_parameter`** for proper system settings management.

### Module: `my_addons/multichannel_sync/` — files added or changed

| File | Change |
|---|---|
| `__manifest__.py` | Updated — added `product` to `depends`. Added `views/mc_analysis_views.xml` to data load list. Version stays `17.0.1.0.0`. |
| `models/__init__.py` | Updated — imports `mc_analysis_report` at end of chain. |
| `models/mc_product.py` | **Refactored** — added `barcode` (Char, optional EAN), `odoo_product_tmpl_id` (Many2one → `product.template`, optional link), `odoo_product_uom_id` and `odoo_product_ref` (related readonly from linked template). Added `last_push_at` (Datetime) and `last_push_status` (Selection: ok/error/skip) fields to track outbound stock-sync health. `_push_stock_sync()` rewritten: URL now reads from `ir.config_parameter` key `multichannel_sync.integration_service_url`; failures set `last_push_status='error'`; unconfigured URL sets `'skip'`. Removed `from odoo.tools import config` import. |
| `models/mc_channel.py` | **Refactored** — added `last_sync_duration` Float field (seconds elapsed in last pipeline run). `action_run_pipeline()` rewritten: sets `sync_status='syncing'` + commits before running (UI feedback), times the run with `time.time()`, returns detailed breakdown notification (parsed ok/err, processed ok/err, duration). Detailed `_logger` on each step. |
| `models/mc_raw_order.py` | **Refactored** — added `action_reprocess()`: resets error records to `new`, clears all parsed_* fields, posts chatter message. Added total_amount mismatch warning in `_extract_standard_payload()`: logs a WARNING if declared `total_amount` differs from computed item sum by more than 1.0 (accounting for platform-side discounts). Stores declared value unchanged (non-lossy). |
| `models/mc_order.py` | **Refactored** — added `product_count` Integer (computed, count of distinct `product_id` across lines). Added `_compute_product_count()`. Added `action_reset_to_draft()`: resets `cancelled` → `draft`, re-applies stock reservation per line, posts chatter message. |
| `models/mc_analysis_report.py` | **New** — `mc.analysis.report` model (`_auto=False`, SQL view). `init()` creates `CREATE OR REPLACE VIEW mc_analysis_report` joining `mc_order_line → mc_order → mc_product → mc_channel`. Excludes cancelled orders. Fields: `order_id`, `order_name`, `channel_id`, `channel_code`, `product_id`, `product_name`, `internal_sku`, `category`, `order_date`, `state`, `quantity`, `unit_price`, `revenue` (= subtotal). |
| `controllers/controllers.py` | **Refactored + Extended** — API key now read from `ir.config_parameter` key `multichannel_sync.api_key` (fallback: hardcoded dev default). Added `GET /api/mc/stock`: returns available/reserved/on-hand qty per active product; supports `?sku=` and `?skus=` query params for filtering. Added `GET /api/mc/products`: returns full product catalog with active channel mappings per product; supports `?channel=` filter. All endpoints use `sudo()` with justification comment. |
| `views/mc_product_views.xml` | **Updated** — search view: added `barcode` field. Tree view: added `barcode` column (optional). Form view: added `barcode` field to Identification group. Added "Odoo Product Link" notebook tab with `odoo_product_tmpl_id`, `odoo_product_uom_id`, `odoo_product_ref`. Added "Integration Sync Status" sub-group in Inventory tab showing `last_push_at` + `last_push_status`. |
| `views/mc_channel_views.xml` | **Updated** — form view Sync Status group: added `last_sync_duration` field. Stat button box: shows `raw_order_count` and `order_count` as non-clickable stat info badges. |
| `views/mc_raw_order_views.xml` | **Updated** — form header: added "Reprocess" button (visible when `state='error'`). Added server action `action_mc_raw_order_reprocess` bound to list view Action menu. |
| `views/mc_order_views.xml` | **Updated** — list view: added `product_count` column (optional). Form header: added "Reset to Draft" button (visible when `state='cancelled'`). Order lines grid: locked (`readonly`) when `state != 'draft'` — prevents editing confirmed/done lines. Stat button box: added non-clickable `product_count` stat info badge. |
| `views/mc_inventory_monitor_views.xml` | **Updated** — added `view_mc_inventory_monitor_graph` bar chart view (product vs available_qty). Window action `action_mc_inventory_monitor` now uses `tree,graph,form` mode. |
| `views/mc_stock_move_views.xml` | **Updated** — added `view_mc_stock_move_graph` bar chart (signed_quantity by day). Window action now uses `tree,graph` mode. |
| `views/mc_analysis_views.xml` | **New** — Analytics views for `mc.analysis.report`: search (channel/product/category/state/date filters + group-bys), list (read-only tabular), graph "Revenue by Channel" (bar, default), graph "Revenue by Month" (line), pivot "Product × Channel Revenue". Also contains `view_mc_data_freshness_tree` (read-only channel list showing last_sync_at, sync_status, order counts). Window actions: `action_mc_analysis_revenue_by_channel`, `action_mc_analysis_volume_by_month`, `action_mc_analysis_pivot`, `action_mc_data_freshness`. |
| `views/menus.xml` | **Updated** — added **Analytics** section (sequence=50) with 4 sub-menus: Revenue by Channel, Revenue by Month, Product Breakdown, Data Freshness. |
| `security/ir.model.access.csv` | **Updated** — added ACL rows for `mc.analysis.report` (users: read-only, managers: read-only — SQL view, no write). |

### API surface after Phase 5:

| Route | Method | Description |
|---|---|---|
| `/api/mc/raw-order` | POST | Receive normalized order from Integration Service |
| `/api/mc/stock` | GET | Current stock levels (all or filtered by SKU) |
| `/api/mc/products` | GET | Product catalog + active channel mappings |
| `/api/mc/stock-update` | POST | **Outbound push target** on Integration Service (called by Odoo when stock changes) |

### ir.config_parameter keys added:

| Key | Purpose |
|---|---|
| `multichannel_sync.api_key` | API key for all `/api/mc/*` routes. Default: `mc-integration-secret-2026` |
| `multichannel_sync.integration_service_url` | Base URL of FastAPI Integration Service for outbound stock push |

---


