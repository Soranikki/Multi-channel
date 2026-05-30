import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import websockets
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from odoo_client import OdooRpcClient


class ReactivateRequest(BaseModel):
    snapshot: dict[str, Any] | None = None


app = FastAPI(title="Odoo WebSocket Connector")
odoo = OdooRpcClient()
status: dict[str, Any] = {
    "connected_to_middleware": False,
    "received_events": 0,
    "ingested_events": 0,
    "outbound_syncs_processed": 0,
    "last_event_id": None,
    "last_result": None,
    "last_error": None,
    "last_outbound_error": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "y"}


async def consume_normalized_events() -> None:
    middleware_url = os.getenv("MIDDLEWARE_WS_URL", "ws://middleware:8020/ws/odoo")
    while True:
        try:
            async with websockets.connect(middleware_url) as websocket:
                status.update({"connected_to_middleware": True, "last_error": None})
                async for message in websocket:
                    event = json.loads(message)
                    await handle_event(websocket, event)
        except Exception as exc:
            status.update({"connected_to_middleware": False, "last_error": str(exc)})
            print(f"[OdooConnector] disconnected from middleware: {exc}")
            await asyncio.sleep(3)


async def handle_event(websocket, event: dict[str, Any]) -> None:
    event_type = event.get("event_type")
    event_id = event.get("event_id")
    if event_type != "normalized_order.ready":
        await websocket.send(json.dumps({"event_type": "connector.ack", "received_at": utc_now()}))
        return

    status.update({"received_events": status["received_events"] + 1, "last_event_id": event_id})
    payload = dict(event.get("payload") or {})
    payload["_integration_event_id"] = event_id
    payload["_source_event_id"] = event.get("source_event_id")
    payload["_normalized_at"] = event.get("normalized_at")
    try:
        if is_dry_run():
            result = {"status": "dry_run", "external_order_id": payload.get("external_order_id")}
        else:
            result = odoo.ingest_normalized_order(payload)
        status.update({"ingested_events": status["ingested_events"] + 1, "last_result": result, "last_error": None})
        print(f"[OdooConnector] ingested {event_id}: {result}")
        await websocket.send(json.dumps({"event_type": "connector.ack", "event_id": event_id, "result": result}, ensure_ascii=False))
    except Exception as exc:
        status.update({"last_error": str(exc)})
        print(f"[OdooConnector] failed {event_id}: {exc}")
        await websocket.send(json.dumps({"event_type": "connector.nack", "event_id": event_id, "error": str(exc)}, ensure_ascii=False))


async def poll_outbound_stock_syncs() -> None:
    middleware_api = os.getenv("MIDDLEWARE_API_URL", "http://middleware:8020/api/outbound/inventory")
    while True:
        try:
            if not is_dry_run():
                records = odoo.get_pending_stock_syncs()
                if records:
                    done_ids = []
                    async with httpx.AsyncClient() as client:
                        for record in records:
                            channel_code = record.get("channel_code")
                            if not channel_code:
                                done_ids.append(record["id"])
                                continue
                            
                            payload = {
                                "platform": channel_code,
                                "external_sku": record.get("external_sku"),
                                "synced_qty": record.get("qty_to_sync", 0.0)
                            }
                            resp = await client.post(middleware_api, json=payload, timeout=10.0)
                            if resp.status_code in (200, 201):
                                done_ids.append(record["id"])
                                status["outbound_syncs_processed"] += 1
                            else:
                                print(f"[OdooConnector] Outbound sync failed for {record['id']}: {resp.text}")
                    
                    if done_ids:
                        odoo.mark_stock_sync_done(done_ids)
                        
            status["last_outbound_error"] = None
        except Exception as exc:
            status["last_outbound_error"] = str(exc)
            print(f"[OdooConnector] Outbound sync polling error: {exc}")
        
        await asyncio.sleep(5)


@app.post("/api/channel/{code}/archive")
async def archive_channel_config(code: str) -> dict[str, Any]:
    middleware_url = os.getenv("MIDDLEWARE_URL", "http://middleware:8020").rstrip("/")
    async with httpx.AsyncClient() as client:
        get_resp = await client.get(f"{middleware_url}/api/channel-configs/{code}", timeout=10.0)
        if get_resp.status_code == 404:
            return {"snapshot": None, "warning": "No middleware config found for this channel."}
        if get_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Middleware GET failed: {get_resp.status_code}")
        snapshot = get_resp.json()
        del_resp = await client.delete(f"{middleware_url}/api/channel-configs/{code}", timeout=10.0)
        if del_resp.status_code not in (204, 404):
            print(f"[OdooConnector] Warning: DELETE middleware config returned {del_resp.status_code}")
        return {"snapshot": snapshot}


@app.post("/api/channel/{code}/reactivate")
async def reactivate_channel_config(code: str, body: ReactivateRequest) -> dict[str, Any]:
    if not body.snapshot:
        return {"status": "ok", "message": "No snapshot to restore."}
    middleware_url = os.getenv("MIDDLEWARE_URL", "http://middleware:8020").rstrip("/")
    async with httpx.AsyncClient() as client:
        post_resp = await client.post(f"{middleware_url}/api/channel-configs", json=body.snapshot, timeout=10.0)
        if post_resp.status_code == 409:
            return {"status": "ok", "message": "Config already exists on middleware."}
        if post_resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Middleware POST failed: {post_resp.status_code}")
        return {"status": "ok", "message": "Config restored on middleware."}


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(consume_normalized_events())
    asyncio.create_task(poll_outbound_stock_syncs())


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "odoo-ws-connector", "dry_run": is_dry_run(), **status}
