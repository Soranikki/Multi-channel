import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.normalizer import normalize_event
from app.raw_store import build_store
from app.channel_config import ChannelConfig, config_store
from app.data.default_configs import SEED_CONFIGS


app = FastAPI(title="Multichannel Integration Middleware")
store = build_store()
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "middleware",
        "odoo_clients": len(odoo_clients),
        "config_count": len(config_store.list()),
    }


@app.get("/raw-events")
def raw_events(limit: int = 100) -> list[dict[str, Any]]:
    return store.read("raw_events.jsonl", limit=limit)


@app.get("/normalized-events")
def normalized_events(limit: int = 100) -> list[dict[str, Any]]:
    return store.read("normalized_events.jsonl", limit=limit)


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


@app.websocket("/ws/odoo")
async def ws_odoo(websocket: WebSocket) -> None:
    await websocket.accept()
    async with odoo_clients_lock:
        odoo_clients.add(websocket)
    await websocket.send_json({"event_type": "middleware.connected", "sent_at": utc_now()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with odoo_clients_lock:
            odoo_clients.discard(websocket)


@app.websocket("/ws/platform/{platform}")
async def ws_platform(websocket: WebSocket, platform: str) -> None:
    await websocket.accept()
    platform = platform.strip().lower()
    await websocket.send_json({"status": "connected", "platform": platform, "sent_at": utc_now()})
    while True:
        try:
            event = await websocket.receive_json()
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
            await broadcast_to_odoo(normalized_event)
            await websocket.send_json({"status": "ack", "event_id": event_id, "normalized": True})
        except WebSocketDisconnect:
            break
        except Exception as exc:
            await websocket.send_json({"status": "nack", "error": str(exc)})
