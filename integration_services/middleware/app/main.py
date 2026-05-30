import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.normalizer import normalize_event
from app.raw_store import build_store
from app.adapters import shopee_adapter, tiktok_adapter


app = FastAPI(title="Multichannel Integration Middleware")
store = build_store()
odoo_clients: set[WebSocket] = set()
odoo_clients_lock = asyncio.Lock()


class InventoryUpdate(BaseModel):
    platform: str
    external_sku: str
    synced_qty: float


@app.post("/api/outbound/inventory")
async def sync_inventory_to_platform(payload: InventoryUpdate) -> dict[str, Any]:
    platform = payload.platform.strip().lower()
    try:
        if platform == "shopee":
            await shopee_adapter.push_inventory(payload.external_sku, payload.synced_qty)
        elif platform == "tiktok":
            await tiktok_adapter.push_inventory(payload.external_sku, payload.synced_qty)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
        
        return {"status": "dispatched", "platform": platform, "sku": payload.external_sku, "qty": payload.synced_qty}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "middleware", "odoo_clients": len(odoo_clients)}


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
            # Receive ACK/heartbeat messages from the Odoo connector to keep the socket alive.
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
