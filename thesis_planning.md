## Current State Summary

Your `sales_analysis` module today is a **read-only dashboard layer** on top of Odoo's native `sale.report`. It has:
- 1 custom model (`sales.analysis.preset`) for saving filter configs
- 4 chart views on native `sale.report`
- Zero custom business models, zero pipeline, zero inventory

**Everything needs to be built from scratch with custom models** to demonstrate your own engineering work for the thesis.

---

## Architecture Decision: Two Modules

| Module | Purpose | Role |
|---|---|---|
| **`multichannel_sync`** | Core data management, pipeline, business logic, inventory, simulation | The operational engine |
| **`sales_analysis`** | Rewritten: analytics dashboards, reporting, data freshness monitoring | The analytical layer |

**Why two modules instead of one:**
- Demonstrates Odoo module architecture and dependency management (good for thesis scoring)
- Clean separation: operational data management vs. analytical reporting
- `sales_analysis` depends on `multichannel_sync`, showing proper `depends` chain
- Each module has a clear, defensible purpose in your thesis paper

**Dependencies:**
```
multichannel_sync  →  depends: ['base', 'mail']
sales_analysis     →  depends: ['multichannel_sync']
```

No dependency on `sale_management`, `stock`, `purchase`, or any other native Odoo business module. Everything is custom-built.

---

## Model Architecture

### Module: `multichannel_sync`

```text
┌──────────────────────────┐
│   Integration Service    │ ← Shopee, TikTok Shop, etc.
│ (FastAPI, Normalization) │
└────────────┬─────────────┘
             │ Standard JSON Contract
             ▼
     ┌───────────────┐
     │  HTTP POST    │
     │ /api/mc/...   │
     └───────┬───────┘
             │ channel_id
             ▼
┌──────────────────────────┐
│        mc.channel        │
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────┐       ┌──────────────────────────┐
│  mc.product.mapping │──────▶│      mc.product          │
│  (external_sku →    │       │  (internal SKU, stock)   │
│   internal product) │       │                          │
└─────────────────────┘       └──────────┬───────────────┘
         ▲                               │
         │ mapping resolution            │ product_id
         │                               ▼
┌─────────────────┐   pipeline   ┌───────────────────┐
│  mc.raw.order   │ ──────────▶  │    mc.order       │
│ (Standard JSON) │              │  (normalized)     │
│  state: new →   │              │  state: draft →   │
│  parsed/error   │              │  confirmed → done │
└─────────────────┘              └────────┬──────────┘
                                          │ O2M
                                          ▼
                                 ┌───────────────────┐
                                 │  mc.order.line    │
                                 │  (product, qty,   │
                                 │   price, subtotal)│
                                 └───────────────────┘

Cross-cutting:
┌──────────────────┐    ┌──────────────────┐
│  mc.stock.move   │    │  mc.sync.log     │
│  (in/out/adjust, │    │  (info/warn/err, │
│   product, qty)  │    │   channel, ref)  │
└──────────────────┘    └──────────────────┘
```

### Model Details

| Model | `_name` | Purpose | Key Fields |
|---|---|---|---|
| **Channel** | `mc.channel` | Define sales platforms | `name`, `code` (shopee/tiktok/manual), `active`, `last_sync_at`, `sync_status` |
| **Product** | `mc.product` | Internal product master (SSOT) | `name`, `internal_sku`, `description`, `category`, `sale_price`, `cost_price`, `stock_qty`, `stock_reserved_qty`, `low_stock_threshold`, `active` |
| **Product Mapping** | `mc.product.mapping` | External SKU → internal product | `channel_id`, `product_id`, `external_sku`, `external_name`, `is_active`; **unique constraint**: `(channel_id, external_sku)` |
| **Raw Order** | `mc.raw.order` | Unprocessed incoming data | `channel_id`, `external_order_id`, `raw_payload` (Text/JSON), `state` (new/parsed/processed/error), `error_message`, `received_at`, `processed_at`, `order_id` (link to processed order) |
| **Order** | `mc.order` | Normalized processed order | `name` (sequence), `channel_id`, `external_order_id`, `customer_name`, `customer_phone`, `customer_email`, `shipping_address`, `order_date`, `state` (draft/confirmed/done/cancelled), `total_amount`, `currency_id`, `line_ids`, `raw_order_id`, `notes` |
| **Order Line** | `mc.order.line` | Order line items | `order_id`, `product_id`, `mapping_id`, `external_sku`, `product_name`, `quantity`, `unit_price`, `discount`, `subtotal` |
| **Stock Move** | `mc.stock.move` | Inventory movement log | `product_id`, `move_type` (in/out/adjustment), `quantity`, `reference`, `channel_id`, `note`, `move_date` |
| **Sync Log** | `mc.sync.log` | Processing & error log | `channel_id`, `log_type` (info/warning/error), `message`, `raw_order_id`, `timestamp` |

### Module: `sales_analysis` (rewritten)

| Model | `_name` | Purpose |
|---|---|---|
| **Analysis Report** | `mc.analysis.report` | SQL view (`_auto = False`) joining `mc.order`, `mc.order.line`, `mc.product`, `mc.channel` for aggregated analytics |
| **Analysis Preset** | `mc.analysis.preset` | Saved dashboard configurations (evolved from current `sales.analysis.preset`, now reading from custom models) |

---

## Phased Implementation Plan

### Phase 1: Data Foundation (Week 1-2)

**Goal:** All core models exist with views, security, and basic CRUD.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 1.1 | Scaffold `multichannel_sync` module with proper `__manifest__.py`, icon, `__init__.py` structure | Module installs cleanly with `--stop-after-init` | — |
| 1.2 | Create `mc.channel` model + form/list/search views + seed data (Shopee, TikTok Shop) | Can create/view/edit channels in UI. Two channels pre-loaded via `data/` XML. | 1.1 |
| 1.3 | Create `mc.product` model + form/list/kanban/search views | Can create products with internal SKU, prices, stock fields visible. | 1.1 |
| 1.4 | Create `mc.product.mapping` model + views + inline on product form | Can map an external SKU to a product per channel. SQL constraint prevents duplicates. | 1.2, 1.3 |
| 1.5 | Create security groups (`mc_user`, `mc_manager`), `ir.model.access.csv`, record rules | All models have explicit ACLs. Manager sees all, user sees own company. | 1.2-1.4 |
| 1.6 | Create menu structure under a top-level "Multichannel" app menu | All views accessible from organized menus. | 1.2-1.5 |
| 1.7 | Create `mc.sync.log` model + list view | Can view sync/processing logs in a dedicated menu. | 1.1, 1.5 |

**Deliverable:** A working Odoo app where you can manage channels, products, and product mappings. No pipeline yet, but the data foundation is solid.

---

### Phase 2: Raw Data Ingestion & API Contract (Week 3-4)

**Goal:** Raw orders can be received via an API endpoint as standardized payloads and parsed.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 2.1 | Create `mc.raw.order` model with state machine (new → parsed → processed → error) | Model installs. State field with proper transitions visible. | Phase 1 |
| 2.2 | Create form/list/search views for raw orders with state filters and color-coded kanban | Can browse raw orders filtered by channel, state. Error orders highlighted. | 2.1 |
| 2.3 | Define Standard Payload Contract | Documented JSON schema that Integration Service uses to send to Odoo. | — |
| 2.4 | Create HTTP Controller `POST /api/mc/raw-order` | FastAPI integration service can push normalized JSON payloads directly into Odoo. Handles auth and channel resolution. | 2.1, 2.3 |
| 2.5 | Implement `_extract_standard_payload()` method | Parsing a raw order extracts the standard contract: external_order_id, customer info, line items. State moves to `parsed` or `error`. | 2.1, 2.3 |
| 2.6 | Implement error handling: missing fields, malformed JSON, unknown channel | Parsing errors set state=`error` with clear `error_message`. A sync log entry is created. | 2.5, 1.7 |
| 2.7 | Add "Parse" action button on raw order form and "Parse All New" button on list view | User can manually trigger parsing from UI. | 2.5 |

**Deliverable:** Odoo exposes an API endpoint to receive normalized payloads from the Integration Service. JSON payloads are stored and parsed into structured intermediate data. Errors are captured and visible.

---

### Phase 3: Order Processing Pipeline (Week 5-6)

**Goal:** Parsed raw orders are transformed into normalized orders with product mapping resolution.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 3.1 | Create `mc.order` model with state machine (draft → confirmed → done / cancelled) | Model installs with sequence-generated name (e.g., `ORD/2026/00001`). | Phase 1 |
| 3.2 | Create `mc.order.line` model | Model installs linked to mc.order via O2M. | 3.1 |
| 3.3 | Create form/list/search views for mc.order with state-based header buttons (Confirm, Mark Done, Cancel) | Full order management UI with channel filters, date filters, state workflow buttons. | 3.1, 3.2 |
| 3.4 | Implement `_resolve_product_mapping()` method | Given a channel + external_sku, returns the internal `mc.product` or raises a mappable error. | Phase 1 |
| 3.5 | Implement `_process_raw_order()` pipeline method | Takes a parsed raw order → resolves mappings → creates `mc.order` + `mc.order.line` records → sets raw order state to `processed` and links the created order. | 2.5, 3.1, 3.2, 3.4 |
| 3.6 | Handle unmapped SKU scenario | If an external SKU has no mapping, raw order state → `error` with message "Unmapped SKU: {sku} on channel {channel}". Log entry created. Does NOT create partial orders. | 3.5, 1.7 |
| 3.7 | Add "Process" button on raw order form and "Process All Parsed" on list view | User can trigger processing from UI. Batch processing works. | 3.5 |
| 3.8 | Add `_sql_constraints` for idempotency | `unique(channel_id, external_order_id)` on `mc.order` prevents duplicate order creation from reprocessing. | 3.1 |
| 3.9 | Implement full pipeline method: `action_run_pipeline()` on channel model | One-click: takes all `new` raw orders for a channel → parse → process. Returns summary action or notification. | 2.5, 3.5 |

**Deliverable:** Complete pipeline: Raw JSON → Parse → Map Products → Create Normalized Order. Duplicate-safe, error-tracked, with manual trigger buttons.

---

### Phase 4: Inventory Management & Business Logic (Week 7-8)

**Goal:** Stock levels are tracked, deducted on order confirmation, and protected against overselling.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 4.1 | Add stock fields to `mc.product`: `stock_qty` (current), `reserved_qty` (pending confirmation), `available_qty` (computed: stock - reserved), `low_stock_threshold` | Fields visible on product form. Available qty computed correctly. | Phase 1 |
| 4.2 | Create `mc.stock.move` model + list view | Stock movements are logged with move_type, quantity, reference, timestamp. | 4.1 |
| 4.3 | Implement `action_confirm_order()` on `mc.order` | Confirming an order: checks available stock for each line → deducts `stock_qty` → creates `mc.stock.move` (type=out) per line → state=`confirmed`. | 3.1, 4.1, 4.2 |
| 4.4 | Implement overselling prevention | If any line's quantity > product's `available_qty`, confirmation is blocked with a `UserError` listing which products are insufficient and by how much. | 4.3 |
| 4.5 | Implement `action_cancel_order()` on `mc.order` | Cancelling a confirmed order: restores stock → creates `mc.stock.move` (type=in, reference=cancellation) → state=`cancelled`. Draft orders cancel without stock changes. | 4.3 |
| 4.6 | Implement stock reservation on order creation (draft) | When a draft order is created from pipeline, `reserved_qty` increases. On confirm, reserved decreases and actual stock decreases. On cancel draft, reserved decreases. | 4.3, 3.5 |
| 4.7 | Add manual stock adjustment wizard | A simple wizard to add/remove stock with a reason. Creates `mc.stock.move` (type=adjustment). Accessible from product form. | 4.2 |
| 4.8 | Add stat buttons to product form: "Stock Moves" (count + link), "Pending Orders" (count) | Product form shows quick access to related stock history and orders. | 4.2, 3.1 |
| 4.9 | Create inventory monitoring list view: products sorted by available_qty, color-coded low stock | Dedicated "Inventory" menu showing stock status at a glance with search filters for low stock. | 4.1 |

**Deliverable:** Full inventory lifecycle: stock in → order created (reserved) → order confirmed (deducted) → order cancelled (restored). Overselling prevented. Stock movements auditable.

---

### Phase 5: Analytics & Dashboard Rewrite (Week 9-10)

**Goal:** Replace current `sales_analysis` with dashboards reading from custom models.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 5.1 | Rewrite `sales_analysis` `__manifest__.py`: depends on `multichannel_sync`, remove `sale_management` dependency | Module installs cleanly with new dependency. | Phase 1-4 |
| 5.2 | Create `mc.analysis.report` SQL view model (`_auto = False`) | SQL view joins `mc_order`, `mc_order_line`, `mc_product`, `mc_channel`. Fields: channel, product, order_date, quantity, revenue, state. Deterministic, company-aware. | Phase 3 |
| 5.3 | Create graph/pivot/list views on `mc.analysis.report` | Revenue by channel (bar chart), order volume by month (line chart), product sales (pivot). | 5.2 |
| 5.4 | Create "Revenue by Channel" dashboard action | Graph view: X=channel, Y=total_revenue. Filterable by date range. | 5.3 |
| 5.5 | Create "Order Volume" dashboard action | Graph view: X=month, Y=order count. Grouped by channel. | 5.3 |
| 5.6 | Create "Low Stock Alerts" list view | Products where `available_qty <= low_stock_threshold`. Sorted by urgency. Accessible from analytics menu. | 4.1 |
| 5.7 | Create "Data Freshness" view | Display channels with `last_sync_at`, time since last sync, sync status. Color-code stale channels. | 1.2 |
| 5.8 | Rewrite/adapt `mc.analysis.preset` model | Presets now filter on `mc.analysis.report` instead of `sale.report`. Computed KPIs read from custom data. | 5.2 |
| 5.9 | Create menu structure for analytics app | Organized: Overview, By Channel, By Product, Low Stock Alerts, Data Freshness, Presets. | 5.3-5.8 |
| 5.10 | Rewrite summary page controller + QWeb template | Summary page now shows custom model data. JSON endpoint returns custom metrics. | 5.8 |

**Deliverable:** Complete analytics layer reading exclusively from custom models. Dashboards show processed data, not raw data. Low stock alerts and data freshness are new capabilities.

---

### Phase 6: Simulation, Testing & Polish (Week 11-12)

**Goal:** Demo-ready system with one-click simulation and proper error visibility.

| # | Task | Done When | Depends On |
|---|---|---|---|
| 6.1 | Create "Simulate Incoming Orders" wizard on `mc.channel` | Button on channel form: generates N random raw orders with realistic mock payload (randomized products, quantities, customer names). Uses the **Standard Payload Contract**. | Phase 2 |
| 6.2 | Create "Run Full Pipeline" button on channel form | One click: simulate → parse all → process all for a channel. Shows result notification (X orders created, Y errors). | 6.1, 3.9 |
| 6.3 | Add "Reprocess" button on error raw orders | Clears error state, resets to `new`, allows re-running the pipeline after fixing data/mappings. | Phase 2 |
| 6.4 | Create error log dashboard | Dedicated view: all sync logs filtered by type=error, grouped by channel, with links to the problematic raw orders. | 1.7 |
| 6.5 | Add demo data XML | Pre-loaded: 2 channels, 10 products, 15 mappings, 5 sample raw orders (mix of success and error scenarios). | Phase 1-3 |
| 6.6 | Write unit tests for pipeline processing | Test: successful parse, successful process, unmapped SKU error, duplicate order idempotency, stock deduction, overselling block. | Phase 1-4 |
| 6.7 | Add chatter (mail.thread) to `mc.order` and `mc.raw.order` | State changes logged in chatter. Provides audit trail. | Phase 2-3 |
| 6.8 | Polish: add `static/description/icon.png` for both modules, clean up manifests, add `installable_info` | Both modules presentable in Odoo app list. | All |
| 6.9 | Validation: install both modules on a fresh DB, run full simulation, verify dashboards show correct data | End-to-end demo works cleanly. | All |

**Deliverable:** Demo-ready system. One-click simulation generates data flowing through the entire pipeline. Dashboards reflect the processed results. Errors are visible and recoverable.

---

## Minimal Viable Demo (MVP)

If time runs short, these are the **non-negotiable core features** to demonstrate a working system:

| Priority | Feature | From Phase |
|---|---|---|
| **MUST** | `mc.channel`, `mc.product`, `mc.product.mapping` models with CRUD views | Phase 1 |
| **MUST** | `mc.raw.order` with Standard Payload API | Phase 2 |
| **MUST** | Parse + Process pipeline (raw → normalized order) | Phase 2-3 |
| **MUST** | `mc.order` with state workflow (draft → confirmed → done) | Phase 3 |
| **MUST** | Stock deduction on order confirmation | Phase 4 |
| **MUST** | At least one chart showing revenue by channel from processed data | Phase 5 |
| **MUST** | Simulate button to generate mock orders | Phase 6 |
| SHOULD | Overselling prevention | Phase 4 |
| SHOULD | Error handling with sync log | Phase 2-3 |
| SHOULD | Low stock alerts view | Phase 5 |
| SHOULD | Stock movement audit log | Phase 4 |
| NICE | Presets / saved dashboard configs | Phase 5 |
| NICE | Reprocess failed orders | Phase 6 |
| NICE | Unit tests | Phase 6 |

---

## What the Final System Demonstrates (Thesis Proof Points)

1. **"Data flows from multiple channels into a central system"**
   → External platforms push normalized data into `mc.raw.order` via a single Standard API.

2. **"Data is processed, normalized, and mapped"**
   → Pipeline extracts standard JSON → maps external SKUs to internal products → creates uniform `mc.order` records.

3. **"Inventory and orders are managed consistently"**
   → Order confirmation deducts stock. Overselling is blocked. Cancellation restores stock. Stock moves are logged.

4. **"Dashboard reflects processed (not raw) data"**
   → `mc.analysis.report` SQL view reads from `mc.order` + `mc.order.line`, not from raw payloads. Charts show clean, business-ready metrics.
