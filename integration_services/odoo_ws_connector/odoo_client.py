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
