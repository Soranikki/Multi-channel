# -*- coding: utf-8 -*-
"""
HTTP endpoints for the Integration Service (FastAPI) to push data into Odoo.

These routes are the boundary between the external Integration Service and
the Odoo core. FastAPI normalizes platform-specific data (Shopee, TikTok, etc.)
into the standard contract before calling these endpoints.

Authentication: API key passed in the X-API-Key header.
All endpoints return JSON.
"""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# ── Simple API key auth ───────────────────────────────────────────────────────
# In production this should be stored in ir.config_parameter, not hardcoded.
# For thesis/demo purposes a fixed key is acceptable.
_API_KEY = 'mc-integration-secret-2026'


def _check_api_key() -> bool:
    """Return True if the request carries the correct API key header."""
    return request.httprequest.headers.get('X-API-Key') == _API_KEY


def _json_response(data: dict, status: int = 200) -> http.Response:
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )


class MultichannelIntegrationController(http.Controller):
    """
    Receives normalized order payloads from the FastAPI Integration Service.
    """

    @http.route(
        '/api/mc/raw-order',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def receive_raw_order(self, **_kwargs):
        """
        POST /api/mc/raw-order

        Accepts a standard-format order payload from the Integration Service
        and stores it as an mc.raw.order record in state 'new'.

        Expected body (JSON):
            {
                "channel_code":       "shopee",          # must match mc.channel.code
                "external_order_id":  "250325ABCDEF",
                "order_date":         "2026-03-25T10:00:00",
                "customer_name":      "Nguyen Van A",
                "customer_phone":     "0901234567",
                "shipping_address":   "123 Le Loi, Q1, HCM",
                "currency":           "VND",
                "total_amount":       300000.0,
                "items": [
                    {
                        "external_sku":  "SKU-001",
                        "product_name":  "Widget A",
                        "quantity":      2,
                        "unit_price":    150000.0
                    }
                ]
            }

        Response 201: {"status": "ok", "raw_order_id": <id>}
        Response 400: {"status": "error", "message": "<reason>"}
        Response 401: {"status": "error", "message": "Unauthorized"}
        Response 409: {"status": "error", "message": "Duplicate order"}
        """
        if not _check_api_key():
            return _json_response({'status': 'error', 'message': 'Unauthorized'}, 401)

        # ── Parse request body ─────────────────────────────────────────────
        try:
            body = json.loads(request.httprequest.data or '{}')
        except json.JSONDecodeError as exc:
            return _json_response({'status': 'error', 'message': f'Invalid JSON: {exc}'}, 400)

        channel_code = body.get('channel_code', '').strip()
        if not channel_code:
            return _json_response(
                {'status': 'error', 'message': 'Field "channel_code" is required.'}, 400
            )

        # ── Resolve channel ────────────────────────────────────────────────
        env = request.env(user=request.env.ref('base.user_admin').id)
        channel = env['mc.channel'].sudo().search(
            [('code', '=', channel_code), ('active', '=', True)], limit=1
        )
        if not channel:
            return _json_response(
                {'status': 'error', 'message': f'No active channel with code "{channel_code}".'}, 400
            )

        # ── Store raw payload ──────────────────────────────────────────────
        # Remove channel_code from the payload before storing —
        # it's routing metadata, not part of the order data.
        order_payload = {k: v for k, v in body.items() if k != 'channel_code'}
        external_order_id = str(body.get('external_order_id', '')).strip()

        try:
            raw_order = env['mc.raw.order'].sudo().create({
                'channel_id':        channel.id,
                'external_order_id': external_order_id or False,
                'raw_payload':       json.dumps(order_payload, ensure_ascii=False),
            })
        except Exception as exc:
            error_str = str(exc)
            if 'unique_channel_external_order' in error_str or 'duplicate' in error_str.lower():
                return _json_response(
                    {'status': 'error', 'message': f'Duplicate order: {external_order_id} already exists for channel {channel_code}.'},
                    409,
                )
            _logger.error('Failed to create mc.raw.order: %s', error_str)
            return _json_response({'status': 'error', 'message': f'Internal error: {error_str}'}, 500)

        _logger.info(
            'mc.raw.order created: id=%s channel=%s order=%s',
            raw_order.id, channel_code, external_order_id,
        )
        return _json_response({'status': 'ok', 'raw_order_id': raw_order.id}, 201)
