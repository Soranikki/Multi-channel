import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel

from app.normalizer import normalize_event
from app.resolver import resolve_path
from app.raw_store import build_store
from app.event_store import build_event_store
from app.channel_config import ChannelConfig, config_store
from app.data.default_configs import SEED_CONFIGS


app = FastAPI(title="Multichannel Integration Middleware")
store = build_store()
event_store = build_event_store()
odoo_clients: set[WebSocket] = set()
odoo_clients_lock = asyncio.Lock()


class InventoryUpdate(BaseModel):
    platform: str
    external_sku: str
    synced_qty: float


@app.on_event("startup")
async def startup() -> None:
    config_store.load_defaults(SEED_CONFIGS)


@app.post("/api/outbound/inventory")
async def sync_inventory_to_platform(payload: InventoryUpdate) -> dict[str, Any]:
    platform = payload.platform.strip().lower()
    config = config_store.get(platform)
    if not config or not config.inventory_endpoint:
        raise HTTPException(status_code=400, detail=f"No inventory endpoint configured for platform: {platform}")
    try:
        endpoint = config.inventory_endpoint
        url = endpoint.url.replace("{sku}", payload.external_sku)
        body = {
            k: (str(v).replace("{qty}", str(payload.synced_qty)) if isinstance(v, str) else v)
            for k, v in endpoint.body_template.items()
        }
        async with httpx.AsyncClient() as client:
            if endpoint.method.upper() == "PUT":
                resp = await client.put(url, json=body, timeout=10.0)
            elif endpoint.method.upper() == "POST":
                resp = await client.post(url, json=body, timeout=10.0)
            else:
                raise HTTPException(status_code=500, detail=f"Unsupported HTTP method: {endpoint.method}")
            resp.raise_for_status()
        return {"status": "dispatched", "platform": platform, "sku": payload.external_sku, "qty": payload.synced_qty}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/channel-configs")
def list_configs() -> list[dict[str, Any]]:
    return [c.model_dump() for c in config_store.list()]


@app.get("/api/channel-configs/{platform}")
def get_config(platform: str) -> dict[str, Any]:
    config = config_store.get(platform.strip().lower())
    if not config:
        raise HTTPException(status_code=404, detail=f"No config found for platform '{platform}'")
    return config.model_dump()


@app.post("/api/channel-configs", status_code=201)
def create_config(data: dict[str, Any]) -> dict[str, Any]:
    platform = data.get("platform", "").strip().lower()
    if not platform:
        raise HTTPException(status_code=400, detail="Field 'platform' is required")
    data["platform"] = platform
    if config_store.get(platform):
        raise HTTPException(status_code=409, detail=f"Config for platform '{platform}' already exists")
    try:
        config = ChannelConfig(**data)
        config_store.create(config)
        return config.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/channel-configs/{platform}")
def update_config(platform: str, data: dict[str, Any]) -> dict[str, Any]:
    platform = platform.strip().lower()
    if not config_store.get(platform):
        raise HTTPException(status_code=404, detail=f"No config found for platform '{platform}'")
    data["platform"] = platform
    try:
        config = ChannelConfig(**data)
        config_store.update(platform, config)
        return config.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/channel-configs/{platform}", status_code=204)
def delete_config(platform: str) -> None:
    platform = platform.strip().lower()
    try:
        config_store.delete(platform)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_webhook_secret(platform: str) -> str:
    key = f"WEBHOOK_SECRET_{platform.upper().replace('-', '_')}"
    return os.getenv(key, os.getenv("WEBHOOK_SECRET", "dev-webhook-secret"))


def verify_webhook_signature(platform: str, timestamp: str | None, signature: str | None, body: bytes) -> None:
    if os.getenv("WEBHOOK_VERIFY", "true").strip().lower() in {"0", "false", "no", "n"}:
        return
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature headers")
    secret = get_webhook_secret(platform)
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


@app.get("/health")
def health() -> dict[str, Any]:
    event_db_ok = False
    try:
        event_db_ok = event_store.healthcheck()
    except Exception:
        event_db_ok = False
    return {
        "status": "ok",
        "service": "middleware",
        "odoo_clients": len(odoo_clients),
        "config_count": len(config_store.list()),
        "event_database": "ok" if event_db_ok else "error",
    }


@app.get("/raw-events")
def raw_events(limit: int = 100) -> list[dict[str, Any]]:
    return store.read("raw_events.jsonl", limit=limit)


@app.get("/normalized-events")
def normalized_events(limit: int = 100) -> list[dict[str, Any]]:
    return store.read("normalized_events.jsonl", limit=limit)


@app.get("/api/events")
def list_integration_events(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return event_store.list_events(status=status, limit=limit)


@app.get("/api/events/pending")
def pending_integration_events(limit: int = 100) -> list[dict[str, Any]]:
    return event_store.pending_events(limit=limit)


@app.post("/api/events/{event_id}/ack")
def ack_integration_event(event_id: str) -> dict[str, Any]:
    event_store.mark_delivered(event_id)
    return {"status": "ack", "event_id": event_id}


@app.post("/api/events/{event_id}/fail")
async def fail_integration_event(event_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    error = str(body.get("error") or "Unknown delivery error") if isinstance(body, dict) else "Unknown delivery error"
    event_store.mark_failed(event_id, error)
    return {"status": "nack", "event_id": event_id}


async def broadcast_to_odoo(message: dict[str, Any]) -> None:
    stale_clients: list[WebSocket] = []
    async with odoo_clients_lock:
        clients = list(odoo_clients)
    for client in clients:
        try:
            await client.send_json(message)
        except RuntimeError:
            stale_clients.append(client)
    if stale_clients:
        async with odoo_clients_lock:
            for client in stale_clients:
                odoo_clients.discard(client)


async def normalize_queue_and_dispatch(platform: str, event: dict[str, Any]) -> dict[str, Any]:
    event_id = event.get("event_id") or f"evt-{platform}-{uuid4().hex}"
    event["event_id"] = event_id
    event["platform"] = platform
    event.setdefault("received_at", utc_now())
    store.append("raw_events.jsonl", event)

    normalized_payload = normalize_event(platform, event)
    normalized_event = {
        "event_id": f"norm-{event_id}",
        "source_event_id": event_id,
        "event_type": "normalized_order.ready",
        "platform": platform,
        "normalized_at": utc_now(),
        "payload": normalized_payload,
    }
    store.append("normalized_events.jsonl", normalized_event)
    event_store.queue_event(event, normalized_event)
    await broadcast_to_odoo(normalized_event)
    return normalized_event


@app.websocket("/ws/odoo")
async def ws_odoo(websocket: WebSocket) -> None:
    await websocket.accept()
    async with odoo_clients_lock:
        odoo_clients.add(websocket)
    await websocket.send_json({"event_type": "middleware.connected", "sent_at": utc_now()})
    try:
        while True:
            message = await websocket.receive_text()
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            event_id = event.get("event_id")
            if event_type == "connector.ack" and event_id:
                event_store.mark_delivered(event_id)
            elif event_type == "connector.nack" and event_id:
                event_store.mark_failed(event_id, str(event.get("error") or "Connector failed"))
    except WebSocketDisconnect:
        pass
    finally:
        async with odoo_clients_lock:
            odoo_clients.discard(websocket)


@app.post("/webhook/{platform}", status_code=202)
async def platform_webhook(platform: str, request: Request) -> dict[str, Any]:
    platform = platform.strip().lower()
    body = await request.body()
    verify_webhook_signature(
        platform,
        request.headers.get("x-mc-timestamp"),
        request.headers.get("x-mc-signature"),
        body,
    )
    try:
        event = await request.json()
        if not isinstance(event, dict):
            raise ValueError("Webhook payload must be a JSON object")
        normalized_event = await normalize_queue_and_dispatch(platform, event)
        return {"status": "accepted", "event_id": event["event_id"], "normalized_event_id": normalized_event["event_id"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/backfill/{platform}")
async def backfill_platform_orders(platform: str, limit: int = 100) -> dict[str, Any]:
    platform = platform.strip().lower()
    config = config_store.get(platform)
    if not config or not config.orders_endpoint:
        raise HTTPException(status_code=400, detail=f"No orders endpoint configured for platform: {platform}")
    async with httpx.AsyncClient() as client:
        resp = await client.get(config.orders_endpoint, timeout=15.0)
        resp.raise_for_status()
        orders = resp.json()
    if not isinstance(orders, list):
        raise HTTPException(status_code=502, detail="Platform orders endpoint must return a list")
    processed = 0
    for order in orders[:limit]:
        external_order_id = resolve_path(order, config.field_mappings.get("external_order_id", "")) or uuid4().hex
        event = {
            "event_id": f"backfill-{platform}-{external_order_id}",
            "platform": platform,
            "event_type": "order.backfill",
            "sent_at": utc_now(),
            "payload": order,
        }
        await normalize_queue_and_dispatch(platform, event)
        processed += 1
    return {"status": "queued", "platform": platform, "processed": processed}
