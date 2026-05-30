import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import websockets
from fastapi import FastAPI

from odoo_client import OdooRpcClient


app = FastAPI(title="Odoo WebSocket Connector")
odoo = OdooRpcClient()
status: dict[str, Any] = {
    "connected_to_middleware": False,
    "received_events": 0,
    "ingested_events": 0,
    "last_event_id": None,
    "last_result": None,
    "last_error": None,
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


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(consume_normalized_events())


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "odoo-ws-connector", "dry_run": is_dry_run(), **status}
