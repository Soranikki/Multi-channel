import os
import xmlrpc.client
from typing import Any


class OdooRpcClient:
    def __init__(self) -> None:
        self.url = os.getenv("ODOO_URL", "http://host.docker.internal:8069").rstrip("/")
        self.db = os.getenv("ODOO_DB", "Multi-Channel")
        self.username = os.getenv("ODOO_USERNAME", "admin")
        self.password = os.getenv("ODOO_PASSWORD", "admin")
        self.uid: int | None = None

    def authenticate(self) -> int:
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        uid = common.authenticate(self.db, self.username, self.password, {})
        if not uid:
            raise RuntimeError("Odoo authentication failed. Check ODOO_DB, ODOO_USERNAME, and ODOO_PASSWORD.")
        self.uid = int(uid)
        return self.uid

    def ingest_normalized_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.uid:
            self.authenticate()
        models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        result = models.execute_kw(
            self.db,
            self.uid,
            self.password,
            "mc.channel",
            "ingest_normalized_order",
            [payload],
        )
        return result

    def get_pending_stock_syncs(self) -> list[dict[str, Any]]:
        if not self.uid:
            self.authenticate()
        models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        records = models.execute_kw(
            self.db,
            self.uid,
            self.password,
            "mc.stock.sync.queue",
            "search_read",
            [[["state", "=", "pending"]]],
            {"fields": ["id", "external_sku", "qty_to_sync", "channel_id"], "limit": 50}
        )
        # We need the channel_code from channel_id
        if records:
            channel_ids = list({r["channel_id"][0] for r in records if r.get("channel_id")})
            channels = models.execute_kw(
                self.db, self.uid, self.password,
                "mc.channel", "search_read",
                [[["id", "in", channel_ids]]],
                {"fields": ["id", "code"]}
            )
            channel_map = {c["id"]: c["code"] for c in channels}
            for r in records:
                if r.get("channel_id"):
                    r["channel_code"] = channel_map.get(r["channel_id"][0])
        return records

    def mark_stock_sync_done(self, sync_ids: list[int]) -> bool:
        if not sync_ids:
            return True
        if not self.uid:
            self.authenticate()
        models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return models.execute_kw(
            self.db,
            self.uid,
            self.password,
            "mc.stock.sync.queue",
            "write",
            [sync_ids, {"state": "done"}]
        )

