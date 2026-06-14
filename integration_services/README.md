# Realtime Integration Services

This folder contains services outside Odoo. They simulate Shopee/TikTok public integration behavior: platform webhooks notify the middleware, middleware normalizes platform-specific order payloads, then forwards clean orders to Odoo through an internal connector.

## Architecture

```text
mock-shopee-api  --HTTP Webhook--> middleware --WebSocket internal--> odoo-ws-connector --XML-RPC--> Odoo
mock-tiktok-api  --HTTP Webhook----^
```

External platform communication uses HTTP webhook + REST API. WebSocket is only used inside the private service network between middleware and the Odoo connector.

Middleware stores integration events in a dedicated PostgreSQL database (`mc_integration`) managed by the `integration-postgres` container. Odoo business data remains in the separate Odoo PostgreSQL database and is only modified through XML-RPC/ORM.

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
curl http://localhost:8020/api/events
curl http://localhost:8020/api/events/pending
```

Inspect the integration event store directly:

```bash
docker exec mc-integration-postgres psql -U mc_integration -d mc_integration \
  -c "SELECT event_id, platform, external_order_id, status FROM integration_events ORDER BY received_at DESC LIMIT 10;"
```

Trigger a platform backfill from the mock REST API:

```bash
curl -X POST 'http://localhost:8020/api/backfill/shopee?limit=10'
curl -X POST 'http://localhost:8020/api/backfill/tiktok?limit=10'
```

## Demo Goal

- Show raw Shopee/TikTok events received by middleware through signed HTTP webhooks.
- Show normalized orders stored in a durable middleware event store before being pushed to Odoo.
- Show normalized orders pushed to Odoo and stored as `mc.raw.order`, with SKU mapping status checked automatically.

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
