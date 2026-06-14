# Multi‑Channel Integration — Usage Guide

## Kiến trúc

```
Platform API (Shopee, TikTok, Lazada...)
  │
  ▼  WebSocket
Middleware (port 8020)
  │  normalize_event dùng config (field_mappings, items_root, item_mappings)
  │  /api/channel-configs — CRUD config cho từng platform
  │
  ▼  WebSocket (normalized_order.ready)
Odoo WS Connector
  │  XML-RPC → mc.channel.ingest_normalized_order()
  │
  ▼
Odoo (port 8069)
  ├─ mc.raw.order (raw → parse → process)
  ├─ sale.order (kết quả)
  └─ mc.product.mapping (SKU mapping)
```

## Thêm kênh mới (vd: Lazada)

### Bước 1: Tạo channel trong Odoo

Vào menu **Sales → Configuration → Multi‑Channel Channels**, ấn **Create**:

| Field | Value |
|-------|-------|
| Channel Name | `Lazada` |
| Channel Code | `lazada` (quan trọng: khớp với middleware config) |
| Integration Enabled | ☑ (bật real‑time) |
| Middleware Channel Key | `lazada` |
| Strict Stock Check | ☑ (chống overselling) |

### Bước 2: Thêm field mappings trong Middleware

Mở Swagger UI: `http://localhost:8020/docs`

**POST** `/api/channel-configs` với body:

```json
{
  "platform": "lazada",
  "field_mappings": {
    "external_order_id": "order_id",
    "platform_order_status": "status",
    "platform_payment_status": "payment_info.status",
    "customer_name": "buyer.name",
    "customer_phone": "buyer.phone",
    "customer_email": "buyer.email",
    "shipping_address": "shipping.address",
    "order_date": "created_at",
    "total_amount": "price",
    "currency": "currency"
  },
  "items_root": "products",
  "item_mappings": {
    "external_sku": "sku",
    "product_name": "name",
    "quantity": "qty",
    "unit_price": "unit_price"
  },
  "inventory_endpoint": {
    "method": "PUT",
    "url": "http://mock-lazada-api:8013/api/v1/products/{sku}/inventory",
    "body_template": {"qty": "{qty}"}
  }
}
```

Các API khác:
- **GET** `/api/channel-configs` — danh sách config
- **GET** `/api/channel-configs/{platform}` — chi tiết
- **PUT** `/api/channel-configs/{platform}` — sửa
- **DELETE** `/api/channel-configs/{platform}` — xoá

### Bước 3: Tạo product mapping trong Odoo

Vào menu **Sales → Configuration → Product Mappings**, tạo mapping cho từng SKU:

| Channel | External SKU | Odoo Product |
|---------|-------------|--------------|
| Lazada | `FURN-0789` | Bàn làm việc cá nhân |
| Lazada | `E-COM07` | Tủ lớn |

### Bước 4: Kiểm tra

Sau khi platform gửi webhook event vào middleware (port 8020, path `/webhook/lazada`), luồng tự động chạy:

1. Middleware normalize payload dùng config
2. Odoo Connector nhận event → gọi `ingest_normalized_order`
3. Pipeline: **parse → mapping → process → reconcile**
4. Vào Odoo kiểm tra **Sales → Orders → Sales Orders**

## Pipeline chi tiết

Khi `integration_enabled=True`, pipeline chạy **bắt buộc** tất cả các bước:

| Step | Mô tả | Điều kiện lỗi |
|------|-------|--------------|
| **Parse** | Đọc normalized payload, tách thông tin khách hàng / sản phẩm | Thiếu `external_order_id` hoặc `items` |
| **Mapping** | Kiểm tra SKU mapping (`mc.product.mapping`) | SKU chưa mapping → dừng, không process |
| **Process** | Tạo `sale.order` | Overselling (nếu `strict_stock_check` bật) |
| **Reconcile** | Cập nhật trạng thái đơn hàng / thanh toán | Mismatch → warning, không block |

## Các endpoint Middleware

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/health` | Health check |
| GET | `/api/channel-configs` | Danh sách config |
| POST | `/api/channel-configs` | Tạo config mới |
| GET | `/api/channel-configs/{platform}` | Chi tiết config |
| PUT | `/api/channel-configs/{platform}` | Cập nhật config |
| DELETE | `/api/channel-configs/{platform}` | Xoá config |
| POST | `/api/outbound/inventory` | Đẩy stock ra platform |
| GET | `/raw-events?limit=N` | Event thô gần nhất |
| GET | `/normalized-events?limit=N` | Event đã normalize |
| WS | `/ws/odoo` | WebSocket cho Odoo connector |
| POST | `/webhook/{platform}` | Webhook nhận event từ platform |

## Dot‑path notation

`field_mappings` dùng dot‑path để trỏ tới field trong payload:

```
"customer_name": "recipient_address.name"
"total_amount": "payment.total"
"platform_payment_status": "payment_info.status"
```

Middleware dùng `resolver.resolve_path()` để traverse dict keys theo dấu `.`.

## CSV các field bắt buộc trong normalized payload

```python
{
    "channel_code": "lazada",           # khớp với mc.channel.code
    "external_order_id": "ORDER-001",   # unique per channel
    "customer_name": "...",
    "customer_phone": "...",
    "customer_email": "...",
    "shipping_address": "...",
    "order_date": "2026-05-15T08:00:00Z",
    "total_amount": 450000,
    "currency": "VND",
    "platform_order_status": "PENDING",
    "platform_payment_status": "UNPAID",
    "items": [
        {
            "external_sku": "FURN-0789",
            "product_name": "Ghế văn phòng",
            "quantity": 1,
            "unit_price": 450000
        }
    ]
}
```

## Các file quan trọng

| File | Vai trò |
|------|---------|
| `my_addons/mc_core/models/mc_channel.py` | Model channel gốc (code là Char) |
| `my_addons/mc_platform_integration/models/mc_channel.py` | `ingest_normalized_order`, pipeline, cron |
| `my_addons/mc_platform_integration/models/mc_raw_order.py` | Status mapping, reconcile |
| `my_addons/mc_sale_order/models/mc_raw_order.py` | Parse, process, tạo sale.order |
| `my_addons/mc_sale_order/models/sale_order.py` | Kế thừa sale.order, apply channel status |
| `my_addons/mc_product_inventory/models/mc_product_mapping.py` | SKU mapping, synced_qty |
| `integration_services/middleware/app/channel_config.py` | Pydantic model + ConfigStore |
| `integration_services/middleware/app/resolver.py` | Dot‑path resolve |
| `integration_services/middleware/app/normalizer.py` | Normalize dùng config |
| `integration_services/middleware/app/main.py` | FastAPI app, CRUD configs |
| `integration_services/middleware/app/data/default_configs.py` | Seed configs cho Shopee, TikTok |
