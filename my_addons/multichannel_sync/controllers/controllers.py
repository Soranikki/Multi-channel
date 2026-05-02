# -*- coding: utf-8 -*-
"""
HTTP endpoints for the Integration Service (FastAPI) to push data into Odoo
and for Odoo to expose inventory/product data back to the Integration Service.

These routes are the boundary between the external Integration Service and
the Odoo core. FastAPI normalizes platform-specific data (Shopee, TikTok, etc.)
into the standard contract before calling these endpoints.

Authentication: API key passed in the X-API-Key header.
Key is stored in ir.config_parameter: multichannel_sync.api_key
Fallback default for development: 'mc-integration-secret-2026'

All endpoints return JSON.
"""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_DEFAULT_API_KEY = 'mc-integration-secret-2026'


def _get_api_key() -> str:
    """
    Read the API key from ir.config_parameter.
    Falls back to the hardcoded default if not configured.
    Using sudo() is justified: this reads a system config value, not user data.
    """
    return (
        request.env['ir.config_parameter'].sudo()
        .get_param('multichannel_sync.api_key', default=_DEFAULT_API_KEY)
    )


def _check_api_key() -> bool:
    """Return True if the request carries the correct API key header."""
    return request.httprequest.headers.get('X-API-Key') == _get_api_key()


def _json_response(data: dict, status: int = 200) -> http.Response:
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )


class MultichannelIntegrationController(http.Controller):
    """
    Exposes API endpoints for the FastAPI Integration Service.

    Inbound (Integration Service → Odoo):
        POST /api/mc/raw-order     Receive a normalized order payload

    Outbound (Odoo → Integration Service on request):
        GET  /api/mc/stock         Current available_qty per SKU
        GET  /api/mc/products      Product catalog + active mappings
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
            return _json_response(
                {'status': 'error', 'message': f'Invalid JSON: {exc}'}, 400
            )

        channel_code = body.get('channel_code', '').strip()
        if not channel_code:
            return _json_response(
                {'status': 'error', 'message': 'Field "channel_code" is required.'}, 400
            )

        # ── Resolve channel ────────────────────────────────────────────────
        # sudo() + admin user: auth='none' route has no user context
        env = request.env(user=request.env.ref('base.user_admin').id)
        channel = (
            env['mc.channel']
            .sudo()
            .search([('code', '=', channel_code), ('active', '=', True)], limit=1)
        )
        if not channel:
            return _json_response(
                {
                    'status': 'error',
                    'message': f'No active channel with code "{channel_code}".',
                },
                400,
            )

        # ── Store raw payload ──────────────────────────────────────────────
        # Remove channel_code from the payload before storing —
        # it's routing metadata, not part of the order data.
        order_payload = {k: v for k, v in body.items() if k != 'channel_code'}
        external_order_id = str(body.get('external_order_id', '')).strip()

        try:
            raw_order = (
                env['mc.raw.order']
                .sudo()
                .create(
                    {
                        'channel_id': channel.id,
                        'external_order_id': external_order_id or False,
                        'raw_payload': json.dumps(order_payload, ensure_ascii=False),
                    }
                )
            )
        except Exception as exc:
            error_str = str(exc)
            if (
                'unique_channel_external_order' in error_str
                or 'duplicate' in error_str.lower()
            ):
                return _json_response(
                    {
                        'status': 'error',
                        'message': f'Duplicate order: {external_order_id} already exists for channel {channel_code}.',
                    },
                    409,
                )
            _logger.error('Failed to create mc.raw.order: %s', error_str)
            return _json_response(
                {'status': 'error', 'message': f'Internal error: {error_str}'}, 500
            )

        _logger.info(
            'mc.raw.order created: id=%s channel=%s order=%s',
            raw_order.id,
            channel_code,
            external_order_id,
        )
        return _json_response({'status': 'ok', 'raw_order_id': raw_order.id}, 201)

    @http.route(
        '/api/mc/stock',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def get_stock(self, **kwargs):
        """
        GET /api/mc/stock
        GET /api/mc/stock?sku=SKU-001        (filter single SKU)
        GET /api/mc/stock?skus=SKU-001,SKU-002  (filter multiple SKUs)

        Returns current available_qty for all active products (or filtered by SKU).
        Used by the Integration Service to pull stock state before syncing back
        to platforms (Shopee, TikTok).

        Response 200:
            {
                "status": "ok",
                "count": 2,
                "stock": [
                    {"internal_sku": "SKU-001", "available_qty": 42.0, "reserved_qty": 3.0, "stock_qty": 45.0},
                    ...
                ]
            }
        """
        if not _check_api_key():
            return _json_response({'status': 'error', 'message': 'Unauthorized'}, 401)

        env = request.env(user=request.env.ref('base.user_admin').id)
        domain = [('active', '=', True)]

        # Optional SKU filter
        sku_param = kwargs.get('sku', '').strip()
        skus_param = kwargs.get('skus', '').strip()
        if sku_param:
            domain.append(('internal_sku', '=', sku_param))
        elif skus_param:
            sku_list = [s.strip() for s in skus_param.split(',') if s.strip()]
            domain.append(('internal_sku', 'in', sku_list))

        products = env['mc.product'].sudo().search_read(
            domain,
            fields=['internal_sku', 'name', 'available_qty', 'reserved_qty', 'stock_qty'],
            order='internal_sku',
        )

        return _json_response({
            'status': 'ok',
            'count': len(products),
            'stock': [
                {
                    'internal_sku':  p['internal_sku'],
                    'name':          p['name'],
                    'stock_qty':     p['stock_qty'],
                    'reserved_qty':  p['reserved_qty'],
                    'available_qty': p['available_qty'],
                }
                for p in products
            ],
        })

    @http.route(
        '/api/mc/products',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def get_products(self, **kwargs):
        """
        GET /api/mc/products
        GET /api/mc/products?channel=shopee   (filter mappings by channel)

        Returns the product catalog with active channel mappings.
        Used by the Integration Service to build its SKU lookup table for
        mapping Shopee/TikTok platform SKUs to Odoo internal SKUs.

        Response 200:
            {
                "status": "ok",
                "count": 5,
                "products": [
                    {
                        "internal_sku": "SKU-001",
                        "name": "Widget A",
                        "sale_price": 150000.0,
                        "available_qty": 42.0,
                        "mappings": [
                            {"channel": "shopee", "external_sku": "shopee-sku-001"},
                            {"channel": "tiktok", "external_sku": "tiktok-sku-abc"}
                        ]
                    },
                    ...
                ]
            }
        """
        if not _check_api_key():
            return _json_response({'status': 'error', 'message': 'Unauthorized'}, 401)

        env = request.env(user=request.env.ref('base.user_admin').id)
        channel_filter = kwargs.get('channel', '').strip()

        products = env['mc.product'].sudo().search(
            [('active', '=', True)], order='internal_sku'
        )

        result = []
        for product in products:
            mapping_domain = [
                ('product_id', '=', product.id),
                ('is_active', '=', True),
            ]
            if channel_filter:
                mapping_domain.append(('channel_id.code', '=', channel_filter))

            mappings = env['mc.product.mapping'].sudo().search_read(
                mapping_domain,
                fields=['external_sku', 'channel_id'],
            )

            result.append({
                'internal_sku':  product.internal_sku,
                'name':          product.name,
                'sale_price':    product.sale_price,
                'available_qty': product.available_qty,
                'mappings': [
                    {
                        'channel':      m['channel_id'][1] if m['channel_id'] else '',
                        'external_sku': m['external_sku'],
                    }
                    for m in mappings
                ],
            })

        return _json_response({
            'status': 'ok',
            'count': len(result),
            'products': result,
        })

