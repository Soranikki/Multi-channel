# Week 7-8 Realtime Integration Services

This folder contains services outside Odoo. They simulate Shopee/TikTok realtime APIs, normalize platform-specific order payloads in a middleware, then forward clean orders to Odoo.

## Architecture

```text
mock-shopee-api  --WebSocket--> middleware --WebSocket--> odoo-ws-connector --XML-RPC--> Odoo
mock-tiktok-api  --WebSocket----^
```

## Start

```bash
cd integration_services
cp .env.example .env
docker compose up --build
```

For a middleware-only demo without writing to Odoo, set this in `.env`:

```bash
DRY_RUN=true
```

For a full Odoo ingest demo, keep Odoo running first and set real credentials:

```bash
ODOO_URL=http://host.docker.internal:8069
ODOO_DB=Multi-Channel
ODOO_USERNAME=<your login email/user>
ODOO_PASSWORD=<your password>
DRY_RUN=false
```

## Health Checks

```bash
curl http://localhost:8011/health
curl http://localhost:8012/health
curl http://localhost:8020/health
curl http://localhost:8030/health
```

## Inspect Data

```bash
curl http://localhost:8020/raw-events
curl http://localhost:8020/normalized-events
```

## Demo Goal

- Week 7: show raw Shopee/TikTok events received by middleware through WebSocket.
- Week 8: show normalized orders pushed to Odoo and stored as `mc.raw.order`, with SKU mapping status checked automatically.

If Odoo credentials are not ready, set `DRY_RUN=true` in `.env`. The connector will still receive realtime events and print them without writing to Odoo.

## Demo Script

Week 7:

```bash
docker compose up --build
curl http://localhost:8020/raw-events
```

Expected result: raw Shopee/TikTok payloads are persisted in middleware.

Week 8:

```bash
curl http://localhost:8020/normalized-events
curl http://localhost:8030/health
```

Expected result: normalized payloads use one standard structure with `channel_code`, `external_order_id`, customer fields, and normalized item lines. With `DRY_RUN=false`, the connector pushes those events to Odoo through XML-RPC.

In Odoo, open:

```text
Bán hàng Đa kênh → Đơn hàng → Đơn hàng gốc
```

The incoming records should be parsed automatically and show SKU mapping status.
