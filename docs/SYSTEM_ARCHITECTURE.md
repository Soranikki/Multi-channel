# Hệ thống Đa kênh — Kiến trúc & Vận hành

> **Multi-channel E-commerce Integration System**  
> Thesis — Odoo 17 | Python 3.10+ | Docker | Webhook | WebSocket nội bộ | XML-RPC

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Kiến trúc tổng thể](#2-kiến-trúc-tổng-thể)
3. [Odoo Modules](#3-odoo-modules)
4. [Integration Services (Docker)](#4-integration-services-docker)
5. [Luồng dữ liệu](#5-luồng-dữ-liệu)
6. [Pipeline xử lý đơn hàng](#6-pipeline-xử-lý-đơn-hàng)
7. [Safety Stock & Reverse Sync](#7-safety-stock--reverse-sync)
8. [Chi tiết kỹ thuật](#8-chi-tiết-kỹ-thuật)
9. [Sơ đồ tuần tự](#9-sơ-đồ-tuần-tự)
10. [Xử lý lỗi & Edge Cases](#10-xử-lý-lỗi--edge-cases)
11. [Bảo mật & Phân quyền](#11-bảo-mật--phân-quyền)
12. [Cấu hình & Biến môi trường](#12-cấu-hình--biến-môi-trường)
13. [Commands vận hành](#13-commands-vận-hành)

---

## 1. Tổng quan hệ thống

Hệ thống tích hợp bán hàng đa kênh (Multi-channel), cho phép Odoo nhận đơn hàng gần thời gian thực từ các sàn thương mại điện tử (Shopee, TikTok Shop) qua webhook HTTP, xử lý qua pipeline tự động (parse → map → process → reconcile), và đồng bộ tồn kho ngược lại sàn qua REST API.

Thiết kế tách rõ hai boundary:
- **External platform boundary**: Shopee/TikTok Shop dùng webhook HTTP + REST API, đúng mô hình public API của sàn thương mại điện tử.
- **Internal service boundary**: Middleware và Odoo connector dùng WebSocket nội bộ để push event nhanh trong private Docker network. WebSocket không dùng để kết nối trực tiếp với API sàn.

### Repository structure

```
Multi-channel/
├── my_addons/                    # Odoo custom modules
│   ├── mc_core/                  #   Module lõi
│   ├── mc_product_inventory/     #   Sản phẩm & tồn kho
│   ├── mc_sale_order/            #   Đơn hàng & raw orders
│   ├── mc_platform_integration/  #   Tích hợp realtime platform
│   └── multichannel_sync/        #   Legacy (không active)
├── integration_services/         # Docker services
│   ├── mock_shopee_api/          #   Mock Shopee Webhook sender + REST
│   ├── mock_tiktok_api/          #   Mock TikTok Shop Webhook sender + REST
│   ├── middleware/               #   Middleware normalization + routing
│   └── odoo_ws_connector/        #   Connector Odoo ↔ Middleware
├── conf/odoo.conf                # Odoo configuration
└── .venv/                        # Python virtual environment
```

### Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| ERP | Odoo 17 Community |
| Python | 3.10+ |
| Database | PostgreSQL |
| Webhook | HTTP POST + HMAC signature |
| WebSocket nội bộ | `websockets` (Python) |
| REST API | FastAPI + Uvicorn |
| XML-RPC | `xmlrpc.client` (Python) |
| Docker | Docker Compose |
| ORM | Odoo ORM (SQLAlchemy-like) |
| Async | `asyncio`, `httpx.AsyncClient` |

---

## 2. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INTERNET / MOCK PLATFORMS                       │
│                                                                         │
│  ┌───────────────────┐          ┌─────────────────────┐                 │
│  │  Mock Shopee API  │          │  Mock TikTok API    │                 │
│  │  (port 8011)      │          │  (port 8012)        │                 │
│  │  Webhook Sender   │──────────│  Webhook Sender     │                 │
│  │  + REST Server    │ HTTP POST│  + REST Server      │                 │
│  └────────┬──────────┘          └──────────┬──────────┘                 │
│           │                                │                            │
│           └──────────┬─────────────────────┘                            │
│                      │ HTTP Webhook (platform events)                   │
│                      ▼                                                  │
│  ┌──────────────────────────────────────────────┐                       │
│  │           MIDDLEWARE (port 8020)             │                       │
│  │  • Webhook: POST /webhook/{platform}         │                       │
│  │  • WS endpoint: /ws/odoo                     │                       │ 
│  │  • REST: GET /api/events/pending             │                       │
│  │  • REST: POST /api/events/{id}/ack|fail      │                       │
│  │  • REST: POST /api/backfill/{platform}       │                       │
│  │  • REST: POST /api/outbound/inventory        │                       │
│  │  • Normalizer: platform raw → canonical      │                       │
│  │  • Event store: JSONL audit + PostgreSQL DB  │                       │
│  └─────────────────┬────────────────────────────┘                       │
│                    │ WS (normalized events)                             │
│                    ▼                                                    │
│  ┌──────────────────────────────────────────────┐                       │
│  │       ODOO WS CONNECTOR (port 8030)          │                       │
│  │  • consume_normalized_events()               │                       │
│  │  • poll_outbound_stock_syncs()               │                       │
│  │  • XML-RPC client → Odoo                     │                       │
│  └─────────────────────┬────────────────────────┘                       │
│                        │ XML-RPC (port 8069)                            │
└────────────────────────┼────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           ODOO SERVER                                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  mc_platform_integration                                         │    │
│  │  • ingest_normalized_order()  ← entry point cho connector        │    │
│  │  • cron_process_incoming_orders()  (1 phút)                      │    │
│  │  • cron_reconcile_order_payment_status()  (5 phút)               │    │
│  │  • Stale event detection                                         │    │
│  │  • Status mapping (canonical)                                    │    │
│  └────────────────────────────────┬─────────────────────────────────┘    │
│                                   │                                      │
│  ┌────────────────────────────────┴─────────────────────────────────┐    │
│  │  mc_sale_order                                                   │    │
│  │  • _process_raw_order() → upsert SO                              │    │
│  │  • Overselling prevention                                        │    │
│  │  • Phân giải mapping SKU                                         │    │
│  │  • Tạo/cập nhật partner                                          │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  mc_product_inventory                                            │    │ 
│  │  • mc.product.mapping (channel ↔ SKU ↔ product)                  │    │
│  │  • mc_buffer_qty (safety stock)                                  │    │
│  │  • synced_qty = max(0, virtual_available - buffer)               │    │
│  │  • mc.stock.sync.queue (outbound queue)                          │    │
│  │  • cron _cron_queue_stock_updates()  (1 phút)                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │ 
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  mc_core                                                         │    │
│  │  • mc.channel (base model + security)                            │    │
│  │  • mc.sync.log (audit trail)                                     │    │
│  │  • Menus & navigation                                            │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Lý do chọn Webhook ngoài + WebSocket nội bộ

Shopee Open Platform và TikTok Shop Partner API không cung cấp WebSocket public cho phần mềm bên thứ ba. Cơ chế thực tế là webhook HTTP để thông báo sự kiện và REST API để lấy/chỉnh dữ liệu chi tiết. Vì vậy boundary bên ngoài của hệ thống dùng `POST /webhook/{platform}` và mô phỏng chữ ký HMAC bằng các header:

```text
X-MC-Timestamp
X-MC-Signature: sha256=<hmac_sha256(secret, timestamp + "." + raw_body)>
```

WebSocket chỉ được dùng giữa middleware và Odoo connector vì đây là private network do hệ thống kiểm soát. Số lượng kết nối ít, không mở ra Internet, và phù hợp để push event normalized sang connector với độ trễ thấp.

WebSocket nội bộ không phải nguồn dữ liệu duy nhất. Trước khi push, middleware đã ghi event vào durable event store PostgreSQL trong database `mc_integration`. Nếu connector hoặc Odoo bị ngắt, event vẫn ở trạng thái `queued`/`failed`; khi connector reconnect, nó gọi `GET /api/events/pending` để drain lại event.

### 2.2 Lý do tách PostgreSQL Integration DB riêng

Odoo sử dụng PostgreSQL cho dữ liệu nghiệp vụ. Middleware cũng sử dụng PostgreSQL, nhưng tách thành database riêng `mc_integration` để lưu dữ liệu hạ tầng tích hợp:

```text
PostgreSQL
├── Odoo business DB: Multi-Channel
│   ├── sale_order
│   ├── mc_raw_order
│   ├── mc_channel
│   └── product/stock/accounting tables
│
└── Integration DB: mc_integration
    └── integration_events
```

Lý do thiết kế:
- **Tách ownership dữ liệu**: Odoo sở hữu business data; middleware sở hữu integration event state.
- **Không ghi trực tiếp vào bảng nghiệp vụ Odoo**: tạo đơn, cập nhật tồn kho, mapping SKU vẫn đi qua Odoo ORM/XML-RPC để giữ business rules, constraints và security.
- **Production-ready hơn SQLite**: PostgreSQL hỗ trợ concurrent writes, JSONB, index, backup, transaction và dễ mở rộng khi middleware có nhiều worker.
- **Dễ bảo vệ kiến trúc**: dữ liệu event/retry/dead-letter là concern của middleware, không làm bẩn schema nghiệp vụ Odoo.

`integration_events` lưu: `event_id`, `platform`, `external_order_id`, `raw_payload`, `normalized_event`, `status`, `attempt_count`, `last_error`, `next_retry_at`, `delivered_at`.

Status chính:

```text
queued → delivered
queued/failed → failed → dead_letter
```

Nếu middleware restart, event vẫn nằm trong PostgreSQL. Nếu connector/Odoo down, event giữ trạng thái `queued` hoặc `failed` và được connector drain lại qua `GET /api/events/pending`.

Polling vẫn cần thiết để đảm bảo nhất quán cuối cùng:
- Backfill polling: `POST /api/backfill/{platform}` lấy lại đơn từ REST API mock platform.
- Retry polling: event `failed` được retry theo backoff.
- Reconciliation cron: Odoo định kỳ đối soát trạng thái thanh toán/đơn hàng.
- Outbound stock polling: connector poll `mc.stock.sync.queue` để đẩy tồn kho ra middleware/sàn.

---

## 3. Odoo Modules

### 3.1 `mc_core` — Module lõi

**Dependencies**: `base`, `mail`

| Model | Mục đích |
|---|---|
| `mc.channel` | Kênh bán hàng (Shopee, TikTok, Manual). Base model cho các module khác inherit. |
| `mc.sync.log` | Audit trail, ghi log mọi sự kiện đồng bộ. |

**Fields trên `mc.channel`:**
- `name`, `code` (shopee/tiktok/manual), `active`, `sequence`
- `sync_status` (idle/syncing/success/error), `last_sync_at`, `last_sync_duration`

**Security groups:**
- `group_mc_user` — quyền đọc cơ bản
- `group_mc_manager` — quyền quản trị (CRUD)

### 3.2 `mc_product_inventory` — Sản phẩm & Tồn kho

**Dependencies**: `mc_core`, `stock`

**Models:**

| Model | Mục đích |
|---|---|
| `product.product` (inherit) | Thêm trường tồn kho đa kênh |
| `mc.product.mapping` | Map SKU ngoài ↔ product Odoo |
| `mc.stock.sync.queue` | Queue đồng bộ tồn kho ngược ra sàn |

**Fields mới trên `product.product`:**

| Field | Type | Mục đích |
|---|---|---|
| `mc_low_stock_threshold` | Float | Ngưỡng cảnh báo tồn thấp (default=5) |
| `mc_buffer_qty` | Float | Hàng an toàn (safety stock, default=0) |
| `mc_is_low_stock` | Boolean (compute) | `virtual_available ≤ threshold` |
| `mc_mapping_count` | Integer (compute) | Số lượng mapping đang active |

**`mc.product.mapping`:**
- Kết nối: `channel_id` + `external_sku` → `product_id`
- `synced_qty` (compute): `max(0, virtual_available - buffer_qty)` — số lượng thực tế có thể đồng bộ lên sàn
- `last_synced_qty`: Giá trị `synced_qty` lần cuối được queue
- `_cron_queue_stock_updates()`: So sánh `synced_qty` vs `last_synced_qty`, tạo queue item nếu khác

**`mc.stock.sync.queue`:**
- `channel_id`, `mapping_id`, `external_sku`, `qty_to_sync`
- `state`: pending → processing → done / error
- Được connector (external) poll qua XML-RPC, xử lý, và đánh done

### 3.3 `mc_sale_order` — Đơn hàng

**Dependencies**: `mc_product_inventory`, `sale_stock`

**Models:**

| Model | Mục đích |
|---|---|
| `sale.order` (inherit) | Thêm trường đa kênh |
| `sale.order.line` (inherit) | Thêm external SKU + mapping ref |
| `mc.raw.order` | Lưu đơn hàng gốc từ sàn |

**Fields mới trên `sale.order`:**

| Field | Type | Mục đích |
|---|---|---|
| `mc_channel_id` | Many2one | Kênh bán hàng |
| `mc_external_order_id` | Char | ID đơn hàng từ sàn |
| `mc_raw_order_id` | Many2one | Raw order gốc |
| `mc_order_status` | Selection | Trạng thái kênh (pending/confirmed/shipping/delivered/cancelled/refunded) |
| `mc_payment_status` | Selection | Trạng thái thanh toán kênh (pending/paid/failed/refunded) |
| `mc_last_channel_status_at` | Datetime | Thời gian cập nhật cuối |

**Methods chính trên sale.order:**

- `_mc_apply_channel_statuses(order_status, payment_status)`: Áp dụng trạng thái từ kênh lên SO
  - `cancelled/refunded` → `action_cancel()`
  - `confirmed/shipping/delivered` (nếu đang draft) → `action_confirm()`
- `_mc_get_canonical_order_status()`: Map state Odoo → canonical status
- `_mc_get_canonical_payment_status()`: Map payment state Odoo → canonical (dựa trên invoice)

**`mc.raw.order`:**

| Field | Type | Mục đích |
|---|---|---|
| `channel_id` | Many2one | Kênh |
| `external_order_id` | Char | ID từ sàn |
| `raw_payload` | Text | JSON gốc |
| `state` | Selection | new → parsed → processed / error |
| `sale_order_id` | Many2one | SO được tạo ra |

**Key methods:**
- `action_parse()` → `_parse_raw_order()`: Parse JSON → fields chuẩn hóa
- `action_process()` → `_process_raw_order()`: Upsert SO + overselling check
- `action_reprocess()`: Reset error records về new
- `_upsert_sale_order_from_raw()`: Tìm mapping → check overselling → tạo/cập nhật SO
- `_find_or_create_partner()`: Dedup partner theo email → phone → name

**Overselling prevention:**
- Dùng `synced_qty` từ mapping để kiểm tra
- Nếu `requested_qty > mapping.synced_qty` AND `channel.strict_stock_check=True` → UserError

### 3.4 `mc_platform_integration` — Tích hợp Realtime

**Dependencies**: `mc_sale_order`

**Models:** Inherit `mc.channel` + `mc.raw.order`

**Fields mới trên `mc.channel`:**

| Field | Type | Default | Mục đích |
|---|---|---|---|
| `integration_enabled` | Boolean | False | Bật/tắt realtime |
| `auto_parse_orders` | Boolean | True | Tự động parse khi nhận |
| `auto_check_mapping` | Boolean | True | Tự động check mapping |
| `auto_process_orders` | Boolean | True | Tự động tạo SO |
| `auto_reconcile_orders` | Boolean | True | Tự động reconcile |
| `strict_stock_check` | Boolean | True | Chống overselling |
| `last_realtime_received_at` | Datetime | — | Event gần nhất |

**Fields mới trên `mc.raw.order`:**

| Field | Type | Mục đích |
|---|---|---|
| `platform_order_status` | Char | Trạng thái gốc từ sàn |
| `platform_payment_status` | Char | Trạng thái payment gốc |
| `canonical_order_status` | Selection | Trạng thái chuẩn hóa |
| `canonical_payment_status` | Selection | Payment chuẩn hóa |
| `mapping_status` | Selection | unchecked/mapped/partial/unmapped |
| `reconcile_state` | Selection | unchecked/matched/mismatched/skipped |

**Hàm entry point:**

```python
@api.model
def ingest_normalized_order(self, payload: dict) -> dict:
```

1. Parse channel_code + external_order_id từ payload
2. Tìm/cập nhật raw_order
3. Nếu `auto_parse_orders` → parse
4. Nếu `auto_check_mapping` → check mapping
5. Nếu `auto_process_orders` + state=parsed + mapping hợp lệ → process
6. Nếu `auto_reconcile_orders` → reconcile

**Canonical mapping (Shopee → standardized):**

| Platform Status | Canonical |
|---|---|
| UNPAID, PENDING | pending |
| PROCESSING, PICKING, PACKED, PAID, CONFIRMED | confirmed |
| SHIPPING, IN_TRANSIT, READY_TO_SHIP | shipping |
| COMPLETED, DELIVERED, FINISHED | delivered |
| CANCELLED, FAILED, VOID | cancelled |
| REFUNDED | refunded |

**Canonical payment mapping:**

| Platform Status | Canonical |
|---|---|
| PAID, CAPTURED, SUCCESS, SETTLED | paid |
| PENDING, PROCESSING | pending |
| FAILED, CANCELLED, VOID | failed |
| REFUNDED | refunded |

**Stale event detection:**
- So sánh `platform_status_updated_at` giữa event hiện tại và dữ liệu đã lưu
- Nếu event đến có timestamp cũ hơn → `{stale: True}` → bỏ qua + log warning

**Soft payment match:**
- Nếu `canonical_payment_status` khác với actual payment Odoo
- Nhưng Odoo chưa có invoice posted → chấp nhận tạm thay vì báo mismatch

**Cron jobs:**

| Cron | Interval | Method |
|---|---|---|
| MC Process Incoming Orders | 1 phút | `cron_process_incoming_orders()` |
| MC Reconcile Order Payment Status | 5 phút | `cron_reconcile_order_payment_status()` |

---

## 4. Integration Services (Docker)

### 4.1 Docker Compose

```yaml
services:
  middleware:        # port 8020 — Central message broker
  mock-shopee-api:  # port 8011 — Mock Shopee platform
  mock-tiktok-api:  # port 8012 — Mock TikTok platform
  odoo-ws-connector:# port 8030 — Bridge to Odoo
```

### 4.2 mock-shopee-api / mock-tiktok-api

**Mục đích:** Mô phỏng WebSocket platform. Đọc file `data/orders.json`, gửi order events qua WebSocket đến middleware.

**Endpoints:**
| Method | Path | Mục đích |
|---|---|---|
| WS | (client) → middleware | Gửi order events |
| GET | `/health` | Health check |
| GET | `/orders` | Danh sách order mock |
| PUT | `/api/v1/products/{sku}/inventory` | Nhận stock update từ middleware |
| GET | `/api/v1/products/{sku}/inventory` | Trả về stock hiện tại |

**Payload event:**
```json
{
  "event_id": "shopee-ORDER_SN",
  "platform": "shopee",
  "event_type": "order.created",
  "sent_at": "2026-01-01T00:00:00Z",
  "payload": { /* platform-specific format */ }
}
```

### 4.3 Middleware

**Mục đích:** Central message broker. Nhận raw event từ platform, normalize sang format chuẩn, phân phối đến Odoo connector.

**Endpoints:**
| Method | Path | Mục đích |
|---|---|---|
| POST | `/webhook/{platform}` | Nhận webhook events từ platform |
| WS | `/ws/odoo` | Gửi normalized events đến Odoo |
| POST | `/api/outbound/inventory` | Nhận stock update từ Odoo → push đến platform |
| GET | `/raw-events` | Xem raw events đã lưu |
| GET | `/normalized-events` | Xem normalized events đã lưu |
| GET | `/health` | Health check |

**Normalization flow:**
```
Shopee raw format:
{ order_sn, order_status, payment_status, items: [{item_sku, ...}], ... }
  │
  ▼  shopee_adapter.normalize()
  │
Normalized format:
{ channel_code, external_order_id, platform_order_status,
  platform_payment_status, customer_*, items: [{external_sku, ...}], ... }
  │
  ▼  broadcast_to_odoo()
```

**Adapter pattern:**
- `adapters/shopee_adapter.py`: `normalize()`, `push_inventory()`
- `adapters/tiktok_adapter.py`: `normalize()`, `push_inventory()`
- Mỗi platform implement theo format riêng → output chung canonical format

**Outbound inventory flow:**
```
Odoo → Connector → POST /api/outbound/inventory
  → shopee_adapter.push_inventory(sku, qty)
  → PUT mock-shopee-api:8011/api/v1/products/{sku}/inventory
```

### 4.4 Odoo WS Connector

**Mục đích:** Cầu nối giữa middleware và Odoo. Duy trì WebSocket persistent, gọi XML-RPC vào Odoo.

**Async tasks:**

| Task | Chức năng | Interval |
|---|---|---|
| `consume_normalized_events()` | Đọc normalized events từ middleware WS → gọi `ingest_normalized_order()` | Continuous (WebSocket) |
| `poll_outbound_stock_syncs()` | Poll `mc.stock.sync.queue` (pending) → gọi middleware API → đánh done | 5 giây |

**Health response mẫu:**
```json
{
  "status": "ok",
  "dry_run": false,
  "connected_to_middleware": true,
  "received_events": 2,
  "ingested_events": 2,
  "outbound_syncs_processed": 5,
  "last_error": null,
  "last_outbound_error": null
}
```

---

## 5. Luồng dữ liệu

### 5.1 Inbound Order (Platform → Odoo)

```
[Mock Shopee]                     [Mock TikTok]
      │                                │
      │  WebSocket                     │  WebSocket
      ▼                                ▼
┌─────────────────────────────────────────┐
│           MIDDLEWARE (FastAPI)          │
│  • Nhận raw event                       │
│  • Normalize (adapter)                  │
│  • Lưu raw_events.jsonl                 │
│  • Broadcast normalized đến Odoo        │
└──────────────────┬──────────────────────┘
                   │  WebSocket
                   ▼
┌─────────────────────────────────────────┐
│        ODOO WS CONNECTOR                │
│  • Nhận normalized event                │
│  • Gọi XML-RPC ingest_normalized_order  │
│  • Gửi ACK/NACK về middleware           │
└──────────────────┬──────────────────────┘
                   │  XML-RPC (localhost:8069)
                   ▼
┌─────────────────────────────────────────┐
│         ODOO - mc.channel               │
│  ingest_normalized_order()              │
│                                         │
│  1. Tìm channel theo channel_code       │
│  2. Tạo/cập nhật mc.raw.order           │ 
│  3. Parse (nếu bật auto_parse)          │
│  4. Check mapping (nếu bật)             │
│  5. Process → upsert SO (nếu bật)       │
│  6. Reconcile (nếu bật)                 │
└─────────────────────────────────────────┘
```

### 5.2 Outbound Stock Sync (Odoo → Platform)

```
┌─────────────────────────────────────────┐
│     ODOO - mc.product.mapping           │
│  _cron_queue_stock_updates() (1 phút)   │
│  • So sánh synced_qty vs last_synced_qty│
│  • Nếu khác → tạo mc.stock.sync.queue   │
└──────────────────┬──────────────────────┘
                   │  XML-RPC (connector poll)
                   ▼
┌─────────────────────────────────────────┐
│        ODOO WS CONNECTOR                │
│  poll_outbound_stock_syncs() (5 giây)   │
│  • get_pending_stock_syncs()            │
│  • POST /api/outbound/inventory         │
│  • mark_stock_sync_done()               │
└──────────────────┬──────────────────────┘
                   │  HTTP POST
                   ▼
┌─────────────────────────────────────────┐
│           MIDDLEWARE                    │
│  POST /api/outbound/inventory           │
│  → shopee_adapter.push_inventory()      │
│  → tiktok_adapter.push_inventory()      │
└──────────────────┬──────────────────────┘
                   │  HTTP PUT
                   ▼
┌──────────────────┴──────────────────────┐
│  Mock Shopee API  /  Mock TikTok API    │
│  PUT /api/v1/products/{sku}/inventory   │
│  Lưu vào _inventory_store               │
└─────────────────────────────────────────┘
```

---

## 6. Pipeline xử lý đơn hàng

### 6.1 State machine — mc.raw.order

```
        ┌──────┐
        │  new │  ← Đơn mới từ platform
        └──┬───┘
           │ action_parse() / auto_parse
           ▼
        ┌────────┐
        │ parsed │  ← Đã parse thành fields chuẩn
        └──┬─────┘
           │ action_process() / auto_process + check mapping
           ▼
     ┌───────────┐
     │ processed │  ← SO đã được tạo/cập nhật
     └───────────┘

        ┌───────┐
        │ error │  ← Lỗi ở bất kỳ bước nào
        └───┬───┘
            │ action_reprocess()
            ▼
          back to "new"
```

### 6.2 Processing pipeline chi tiết

```
ingest_normalized_order(payload)
  │
  ├── 1. Validate channel_code, external_order_id
  │
  ├── 2. Tìm/cập nhật mc.raw.order (IntegrityError-safe)
  │     ├── CREATE nếu chưa tồn tại
  │     └── UPDATE nếu đã tồn tại (kiểm tra stale event)
  │
  ├── 3. [auto_parse_orders] action_parse()
  │     └── _parse_raw_order()
  │           ├── Load JSON từ raw_payload
  │           ├── _extract_standard_payload() → validate
  │           │     ├── Required: external_order_id, items
  │           │     ├── Mỗi item: external_sku, quantity>0, unit_price
  │           │     └── Format: customer_name/phone/email, address, date
  │           └── Write: state=parsed, fields chuẩn hóa
  │
  ├── 4. [auto_check_mapping] _check_product_mapping()
  │     ├── Search mc.product.mapping theo (channel_id, external_sku)
  │     ├── mapping_status: mapped / partial / unmapped
  │     └── Ghi mapped_product_count + unmapped_skus
  │
  ├── 5. [auto_process_orders + state=parsed + mapping_status in (mapped, unchecked)]
  │     └── action_process() → _process_raw_order()
  │           ├── _upsert_sale_order_from_raw()
  │           │     ├── Duyệt items → tìm mapping cho mỗi SKU
  │           │     ├── [strict_stock_check] Nếu requested > synced_qty → OVERSOLD ERROR
  │           │     ├── Nếu unmapped SKU → USER ERROR
  │           │     ├── _find_or_create_partner() (email → phone → name dedup)
  │           │     ├── Tìm/cập nhật SO theo (channel_id, external_order_id)
  │           │     │     ├── Nếu SO draft → replace order_line
  │           │     │     └── Nếu SO confirmed → chỉ update partner/ref
  │           │     └── Tạo SO mới nếu chưa tồn tại
  │           ├── _apply_channel_status_to_sale_order()
  │           │     └── _mc_apply_channel_statuses(canonical_statuses)
  │           │           ├── Map canonical → Odoo actions
  │           │           │     ├── cancelled/refunded → action_cancel()
  │           │           │     └── confirmed/shipping/delivered → action_confirm()
  │           │           └── Write mc_order_status, mc_payment_status
  │           ├── state=processed, sale_order_id ghi lại
  │           └── savepoint + rollback trên IntegrityError
  │
  └── 6. [auto_reconcile_orders] _reconcile_with_sale_order()
        ├── Nếu không có SO → skipped
        ├── _mc_apply_channel_statuses() (cập nhật lại SO)
        ├── So sánh canonical (desired) vs actual Odoo state
        │     ├── Order match
        │     │     └── _is_order_reconcile_match() — fuzzy match
        │     └── Payment match
        │           ├── Exact match
        │           └── Soft match: nếu chưa có invoice, tạm chấp nhận
        └── Ghi reconcile_state: matched / mismatched / skipped
```

### 6.3 Overselling prevention details

```python
# Công thức tính synced_qty
synced_qty = max(0.0, virtual_available - mc_buffer_qty)

# Kiểm tra
if channel.strict_stock_check:
    if requested_qty > mapping.synced_qty:
        raise UserError(f"Overselling prevented: {sku} (Req: {qty}, Avail: {synced_qty})")
```

- `virtual_available` = `qty_available` + incoming moves - outgoing moves (forecasted)
- `mc_buffer_qty`: Hàng an toàn, không được đồng bộ lên sàn
- `strict_stock_check` có thể tắt theo channel khi cần

---

## 7. Safety Stock & Reverse Sync

### 7.1 Safety Stock (mc_buffer_qty)

```
virtual_available = 100  # Tồn khả dụng (forecasted)
mc_buffer_qty     = 20   # Hàng an toàn
────────────────────────────────────
synced_qty        = 80   # Số lượng sẽ đồng bộ lên sàn

→ Sàn chỉ thấy có 80, overselling check dùng 80
→ 20 là buffer cho Odoo xử lý nội bộ
```

### 7.2 Stock Sync Queue Lifecycle

```
1. Cron 1 phút: _cron_queue_stock_updates()
   → Duyệt active mappings
   → So sánh synced_qty (compute) vs last_synced_qty (stored)
   → Nếu khác: tạo mc.stock.sync.queue (state=pending)

2. Connector poll 5 giây: get_pending_stock_syncs()
   → Đọc queue items (state=pending)
   → POST /api/outbound/inventory cho mỗi item
   → mark_stock_sync_done() → state=done

3. Middleware: POST /api/outbound/inventory
   → Xác định platform (shopee/tiktok)
   → Gọi adapter.push_inventory(sku, qty)
   → Adapter gọi REST API của platform
```

---

## 8. Chi tiết kỹ thuật

### 8.1 XML-RPC — Odoo Remote API

Connector giao tiếp với Odoo qua XML-RPC (port 8069):

```python
# Authenticate
common = xmlrpc.client.ServerProxy("http://odoo:8069/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})

# Call method
models = xmlrpc.client.ServerProxy("http://odoo:8069/xmlrpc/2/object")
result = models.execute_kw(db, uid, password, "mc.channel",
    "ingest_normalized_order", [payload])
```

### 8.2 WebSocket — Real-time Communication

```
Platform → Middleware:  POST /webhook/{platform}   (webhook events)
Middleware → Odoo:      /ws/odoo                   (bidirectional ACK)
```

- Middleware dùng `broadcast_to_odoo()` để gửi đến tất cả Odoo client đang kết nối
- Connector gửi ACK/NACK sau khi xử lý

### 8.3 Savepoint & Rollback

Sử dụng `@api.model` + `with self.env.cr.savepoint()` cho:

- `ingest_normalized_order()`: Bắt `IntegrityError` khi CREATE raw_order (race condition)
- `_process_raw_order()`: Rollback nếu có conflict, giữ nguyên error state
- Cron jobs: Mỗi raw order được xử lý trong savepoint riêng → lỗi không ảnh hưởng toàn bộ batch

### 8.4 Type Hints

Python 3.10+ type hints được dùng cho public API:

```python
def ingest_normalized_order(self, payload: dict[str, Any]) -> dict[str, Any]:
def _prepare_integration_vals_from_payload(self, payload: dict, ...) -> dict:
```

---

## 9. Sơ đồ tuần tự

### 9.1 Inbound Order — thành công

```
Mock API     Middleware     Connector     Odoo mc.channel     mc.raw.order    sale.order
  │             │              │               │                  │               │
  │──WS event──>│              │               │                  │               │
  │             │──normalize──>│               │                  │               │
  │             │<──ACK────────│               │                  │               │
  │             │              │──XML-RPC──────>│                 │               │
  │             │              │               │──create──────────>               │
  │             │              │               │──parse───────────>               │
  │             │              │               │──check_mapping───>               │
  │             │              │               │──process─────────>               │
  │             │              │               │                  │──upsert──────>│
  │             │              │               │──reconcile───────>               │
  │             │              │<──result──────│                  │               │
  │             │<──WS ACK─────│               │                  │               │
```

### 9.2 Overselling — bị chặn

```
Connector     Odoo mc.channel     mc.raw.order     mc.product.mapping
  │               │                   │                   │
  │──XML-RPC──────>                   │                   │
  │               │──create──────────>│                   │
  │               │──parse───────────>│                   │
  │               │──check_mapping───>│                   │
  │               │                   │────search SKU────>│
  │               │                   │<──synced_qty=14───│
  │               │──process─────────>│                   │
  │               │                   │  qty=20 > 14      │
  │               │                   │  raise UserError  │
  │               │<──state=error─────│                   │
  │<──result──────│                   │                   │
```

### 9.3 Outbound Stock Sync

```
Odoo Cron       mc.product.mapping    mc.stock.sync.queue    Connector     Middleware    Mock API
  │                    │                      │                 │             │            │
  │──1 phút────────────>                      │                 │             │            │
  │                    │──compare qty────────>│                 │             │            │
  │                    │──create pending─────>│                 │             │            │
  │                    │                      │                 │             │            │
  │                    │                      │──poll 5 giây───>│             │            │
  │                    │                      │                 │──POST──────>│            │
  │                    │                      │                 │             │──PUT──────>│
  │                    │                      │                 │             │<──200──────│
  │                    │                      │                 │<──200───────│            │
  │                    │<──state=done─────────│                 │             │            │
```

---

## 10. Xử lý lỗi & Edge Cases

| Tình huống | Cách xử lý |
|---|---|
| **Missing channel_code** | ValueError: "Missing channel_code" |
| **Invalid channel** (lazada) | ValueError: "No mc.channel found" |
| **Missing external_order_id** | ValueError: "Missing external_order_id" |
| **Duplicate order (IntegrityError)** | Rollback → search lại → update thay vì create |
| **Stale event** (cập nhật cũ hơn) | `{stale: True}` → bỏ qua + log warning |
| **Empty items list** | state=error, message rõ ràng |
| **Missing external_sku trong item** | state=error: "missing external_sku" |
| **Zero/negative quantity** | state=error: "invalid quantity" |
| **Unmapped SKU** | UserError "Unmapped SKU(s)" |
| **Overselling** (qty > synced_qty) | UserError "Overselling prevented" |
| **SO đã confirmed được update** | Chỉ update partner/ref, không thay đổi order_line |
| **SO cancel thất bại** | Log warning, không crash |
| **Connector mất kết nối WS** | Auto-reconnect sau 3 giây |
| **Odoo server down** | Connector retry trên mỗi event |
| **Dry run mode** | `DRY_RUN=true` → không gọi Odoo, log result giả |

---

## 11. Bảo mật & Phân quyền

### 11.1 Security Groups

| Group | Permissions |
|---|---|
| `mc_core.group_mc_user` | Đọc channel, sync log. CRUD mapping, raw order. |
| `mc_core.group_mc_manager` | Full CRUD trên tất cả models. |

### 11.2 Access Control

**mc_core:**
| Model | User | Manager |
|---|---|---|
| mc.channel | read | CRUD |
| mc.sync.log | read | CRUD |

**mc_product_inventory:**
| Model | User | Manager |
|---|---|---|
| mc.product.mapping | CRUD | CRUD |
| mc.stock.sync.queue | CRUD (no unlink) | CRUD |

**mc_sale_order:**
| Model | User | Manager |
|---|---|---|
| mc.raw.order | CRUD (no unlink) | CRUD |

### 11.3 Authentication

- Odoo XML-RPC: dùng user `dev` với password `123` (qua `.env`)
- Middleware WebSocket: không authentication (mock environment)
- Token/API key có thể thêm sau cho production

### 11.4 Credentials

File `.env` trong `integration_services/`:
```
ODOO_URL=http://host.docker.internal:8069
ODOO_DB=Multi-Channel
ODOO_USERNAME=dev
ODOO_PASSWORD=123
DRY_RUN=false
```

> **Security note:** Môi trường hiện tại dùng mock credentials cho dev.   
> Production cần: mật khẩu mạnh, HTTPS, WS over SSL.

---

## 12. Cấu hình & Biến môi trường

### 12.1 Odoo Config (`conf/odoo.conf`)

```ini
[options]
addons_path = addons, my_addons
db_host = localhost
db_port = 5432
db_user = khanh
db_password = nhachung
xmlrpc_port = 8069
admin_passwd = <hashed_password>
```

### 12.2 Docker Compose Environment

| Service | Variable | Default | Mục đích |
|---|---|---|---|
| mock-shopee-api | `MIDDLEWARE_WEBHOOK_URL` | http://middleware:8020/webhook/shopee | Gửi webhook đến middleware |
| mock-shopee-api | `EVENT_INTERVAL_SECONDS` | 2 | Giãn cách giữa các event |
| mock-shopee-api | `REPLAY_INTERVAL_SECONDS` | 0 | Lặp lại (0 = không) |
| mock-tiktok-api | (same structure) | — | — |
| odoo-ws-connector | `MIDDLEWARE_WS_URL` | ws://middleware:8020/ws/odoo | WS URL |
| odoo-ws-connector | `ODOO_URL` | http://host.docker.internal:8069 | Odoo XML-RPC |
| odoo-ws-connector | `ODOO_DB` | Multi-Channel | Database |
| odoo-ws-connector | `ODOO_USERNAME` | dev | User |
| odoo-ws-connector | `ODOO_PASSWORD` | 123 | Password |
| odoo-ws-connector | `DRY_RUN` | false | Dry run mode |
| odoo-ws-connector | `MIDDLEWARE_API_URL` | http://middleware:8020 | REST URL |
| middleware | `EVENT_STORE_DIR` | /data | Thư mục lưu event |

---

## 13. Commands vận hành

### 13.1 Start / Stop Odoo

```bash
# Start Odoo
cd /home/soranikki/odoo-dev/Multi-channel
source .venv/bin/activate
nohup ./odoo-bin -c conf/odoo.conf -d "Multi-Channel" --dev=xml,qweb &

# Stop Odoo
pkill -f "odoo-bin -c conf/odoo.conf"
```

### 13.2 Upgrade modules

```bash
# Upgrade all custom modules
source .venv/bin/activate
./odoo-bin -c conf/odoo.conf -d "Multi-Channel" \
  -u mc_core,mc_product_inventory,mc_sale_order,mc_platform_integration \
  --stop-after-init
```

### 13.3 Docker Services

```bash
# Build & start all services
cd integration_services
docker compose up -d --build

# View logs
docker compose logs -f

# Restart a specific service
docker compose restart middleware

# Stop all
docker compose down
```

### 13.4 Test & Debug

```bash
# Check health
curl http://localhost:8011/health   # mock-shopee
curl http://localhost:8012/health   # mock-tiktok
curl http://localhost:8020/health   # middleware
curl http://localhost:8030/health   # odoo-ws-connector

# Check raw events ingested
curl http://localhost:8020/normalized-events?limit=5

# Directly send a normalized order (test overselling)
python3 -c "
import xmlrpc.client
uid = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common') \
    .authenticate('Multi-Channel', 'dev', '123', {})
models = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/object')
result = models.execute_kw('Multi-Channel', uid, '123', 'mc.channel',
    'ingest_normalized_order', [{'channel_code': 'shopee', ...}])
print(result)
"

# Check stock sync queue
PGPASSWORD='nhachung' psql -U khanh -h localhost -d "Multi-Channel" \
  -c "SELECT id, external_sku, qty_to_sync, state FROM mc_stock_sync_queue;"
```

---

## Phụ lục

### A. File maps

| Module | Files chính |
|---|---|
| mc_core | `models/mc_channel.py`, `models/mc_sync_log.py` |
| mc_product_inventory | `models/product_product.py`, `models/mc_product_mapping.py`, `models/mc_stock_sync_queue.py`, `data/mc_stock_cron.xml` |
| mc_sale_order | `models/sale_order.py`, `models/mc_raw_order.py` |
| mc_platform_integration | `models/mc_channel.py`, `models/mc_raw_order.py`, `data/mc_realtime_cron.xml` |

### B. Cron summary

| Cron name | Interval | Method | Module |
|---|---|---|---|
| MC Process Incoming Orders | 1 minute | `mc.channel.cron_process_incoming_orders()` | mc_platform_integration |
| MC Reconcile Order Payment Status | 5 minutes | `mc.channel.cron_reconcile_order_payment_status()` | mc_platform_integration |
| MC Push Stock Updates | 1 minute | `mc.product.mapping._cron_queue_stock_updates()` | mc_product_inventory |

### C. Model dependency graph

```
mc.channel (mc_core)
  ├── mc.product.mapping (mc_product_inventory)
  │     └── mc.stock.sync.queue (mc_product_inventory)
  │     └── product.product (inherit, stock)
  ├── mc.raw.order (mc_sale_order → mc_product_inventory)
  │     └── sale.order (inherit, sale_stock)
  └── mc.sync.log (mc_core)
```
