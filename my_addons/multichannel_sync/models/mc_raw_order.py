# -*- coding: utf-8 -*-
"""
mc.raw.order — Raw incoming order storage and parsing.

Design principle:
    Odoo does NOT know about Shopee, TikTok, or any external platform format.
    All platform-specific parsing and normalization is handled by the external
    Integration Service (FastAPI). That service sends a single standardized
    payload to Odoo via the /api/mc/raw-order endpoint.

Standard payload contract (defined by the Integration Service):
    {
        "external_order_id": "250325ABCDEF",
        "order_date":        "2026-03-25T10:00:00",   # ISO 8601 UTC
        "customer_name":     "Nguyen Van A",
        "customer_phone":    "0901234567",
        "shipping_address":  "123 Le Loi, Q1, HCM",
        "currency":          "VND",
        "total_amount":      300000.0,
        "items": [
            {
                "external_sku":  "SKU-001",
                "product_name":  "Widget A",
                "quantity":      2,
                "unit_price":    150000.0
            }
        ]
    }

When a new channel is added (e.g. Lazada), only the FastAPI adapter changes.
This Odoo model remains untouched — it only works with the standard contract.
"""
import json
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Required top-level keys in the standard payload ───────────────────────────
REQUIRED_FIELDS = ('external_order_id', 'items')


class McRawOrder(models.Model):
    """
    Stores one unprocessed standard-format payload per incoming order.

    State machine:
        new       → Payload stored, not yet parsed by Odoo.
        parsed    → Standard payload successfully validated and extracted.
                    Ready to be processed into a normalized mc.order.
        processed → A normalized mc.order was created from this raw order.
        error     → Parsing or processing failed. See error_message.

    The raw_payload field is immutable after creation (append-only audit).
    """
    _name = 'mc.raw.order'
    _description = 'Raw Incoming Order'
    _order = 'received_at desc, id desc'
    _inherit = ['mail.thread']

    # ── Identity ──────────────────────────────────────────────────────────────

    channel_id = fields.Many2one(
        comodel_name='mc.channel',
        string='Channel',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    external_order_id = fields.Char(
        string='External Order ID',
        index=True,
        help='Order identifier from the source platform, as forwarded by the Integration Service.',
    )

    # ── Raw payload (immutable after creation) ────────────────────────────────

    raw_payload = fields.Text(
        string='Raw Payload (JSON)',
        required=True,
        help=(
            'Standard-format JSON payload received from the Integration Service. '
            'Never modified after creation — kept for auditability and reprocessing.'
        ),
    )

    # ── State machine ─────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('new',       'New'),
            ('parsed',    'Parsed'),
            ('processed', 'Processed'),
            ('error',     'Error'),
        ],
        string='State',
        default='new',
        required=True,
        index=True,
        tracking=True,
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
        help='Populated when state=error. Describes why parsing or processing failed.',
    )

    # ── Timestamps ────────────────────────────────────────────────────────────

    received_at = fields.Datetime(
        string='Thời gian nhận',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    parsed_at = fields.Datetime(string='Parsed At',    readonly=True)
    processed_at = fields.Datetime(string='Processed At', readonly=True)

    # ── Parsed intermediate fields ────────────────────────────────────────────
    # Populated by _parse_raw_order(). Consumed by _process_raw_order() in Phase 3.

    parsed_external_order_id = fields.Char(string='Parsed Order ID',     readonly=True)
    parsed_customer_name     = fields.Char(string='Customer Name',        readonly=True)
    parsed_customer_phone    = fields.Char(string='Customer Phone',       readonly=True)
    parsed_shipping_address  = fields.Char(string='Shipping Address',     readonly=True)
    parsed_order_date        = fields.Datetime(string='Order Date',       readonly=True)
    parsed_total_amount      = fields.Float(string='Total Amount', digits=(12, 2), readonly=True)
    parsed_currency          = fields.Char(string='Currency',             readonly=True)
    parsed_items_json        = fields.Text(
        string='Parsed Items (JSON)',
        readonly=True,
        help='JSON list: [{"external_sku": ..., "product_name": ..., "quantity": ..., "unit_price": ...}]',
    )

    # ── Link to resulting order ───────────────────────────────────────────────

    order_id = fields.Many2one(
        comodel_name='mc.order',
        string='Resulting Order',
        readonly=True,
        ondelete='set null',
    )

    # ── SQL constraints ───────────────────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_channel_external_order',
            'UNIQUE(channel_id, external_order_id)',
            'This external order ID has already been received from this channel.',
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # Public UI actions
    # ═════════════════════════════════════════════════════════════════════════

    def action_parse(self):
        """Parse button on form view. Only runs on new/error records."""
        for record in self.filtered(lambda r: r.state in ('new', 'error')):
            record._parse_raw_order()
        return True

    def action_reprocess(self):
        """
        Reprocess button — resets error records back to 'new' so they can be
        re-parsed after fixing mappings or correcting payload data.
        Only applies to records in state 'error'.
        """
        error_records = self.filtered(lambda r: r.state == 'error')
        if not error_records:
            raise UserError('No error records selected to reprocess.')
        error_records.write({
            'state': 'new',
            'error_message': False,
            # Clear parsed fields so a fresh parse starts clean
            'parsed_at': False,
            'parsed_external_order_id': False,
            'parsed_customer_name': False,
            'parsed_customer_phone': False,
            'parsed_shipping_address': False,
            'parsed_order_date': False,
            'parsed_total_amount': False,
            'parsed_currency': False,
            'parsed_items_json': False,
        })
        for rec in error_records:
            rec.message_post(body='Reset to new for reprocessing.')

    def action_parse_all_new(self):
        """
        Called from the list view Action menu.
        Parses every record currently in state 'new', one by one so a single
        failure does not block the rest.
        """
        new_orders = self.search([('state', '=', 'new')])
        if not new_orders:
            raise UserError('No new raw orders to parse.')
        for order in new_orders:
            order._parse_raw_order()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Parsing Complete',
                'message': f'{len(new_orders)} raw order(s) parsed.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_order(self):
        """Navigate to the resulting mc.order from this raw order."""
        self.ensure_one()
        if not self.order_id:
            raise UserError('This raw order has not been processed yet.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Order',
            'res_model': 'mc.order',
            'view_mode': 'form',
            'res_id': self.order_id.id,
        }

    def action_process(self):
        """Process button on form view. Only runs on parsed records."""
        for record in self.filtered(lambda r: r.state == 'parsed'):
            record._process_raw_order()
        return True

    def action_process_all_parsed(self):
        """
        Called from the list view Action menu.
        Processes every record currently in state 'parsed'.
        """
        parsed_orders = self.search([('state', '=', 'parsed')])
        if not parsed_orders:
            raise UserError('No parsed raw orders to process.')
        created = 0
        for order in parsed_orders:
            try:
                order._process_raw_order()
                created += 1
            except Exception:
                pass  # errors are already logged by _process_raw_order
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Processing Complete',
                'message': f'{created} order(s) created successfully.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Parsing — internal
    # ═════════════════════════════════════════════════════════════════════════

    def _parse_raw_order(self) -> None:
        """
        Validate and extract the standard payload into parsed_* fields.

        The payload is expected to be in the standard contract defined by the
        Integration Service — not in any platform-specific format.

        On success: populates parsed_* fields, sets state='parsed'.
        On failure: sets state='error', writes error_message, logs to mc.sync.log.
        """
        self.ensure_one()
        try:
            payload = self._load_json_payload()
            parsed  = self._extract_standard_payload(payload)

            self.write({
                'state':                      'parsed',
                'error_message':              False,
                'parsed_at':                  fields.Datetime.now(),
                'external_order_id':          parsed['external_order_id'],
                'parsed_external_order_id':   parsed['external_order_id'],
                'parsed_customer_name':       parsed['customer_name'],
                'parsed_customer_phone':      parsed['customer_phone'],
                'parsed_shipping_address':    parsed['shipping_address'],
                'parsed_order_date':          parsed['order_date'],
                'parsed_total_amount':        parsed['total_amount'],
                'parsed_currency':            parsed['currency'],
                'parsed_items_json':          json.dumps(parsed['items']),
            })

            self.env['mc.sync.log'].sudo().create({
                'channel_id': self.channel_id.id,
                'log_type':   'info',
                'message':    f'Parsed raw order {parsed["external_order_id"]} successfully.',
                'reference':  parsed['external_order_id'],
            })

        except Exception as exc:
            error_msg = str(exc)
            self.write({'state': 'error', 'error_message': error_msg})
            self.env['mc.sync.log'].sudo().create({
                'channel_id': self.channel_id.id,
                'log_type':   'error',
                'message':    f'Parse failed for raw order #{self.id}: {error_msg}',
                'reference':  self.external_order_id or f'raw#{self.id}',
            })
            _logger.warning('mc.raw.order._parse_raw_order failed id=%s: %s', self.id, error_msg)

    def _load_json_payload(self) -> dict:
        """Decode raw_payload text into a Python dict."""
        if not self.raw_payload or not self.raw_payload.strip():
            raise ValueError('Raw payload is empty.')
        try:
            data = json.loads(self.raw_payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid JSON: {exc}') from exc
        if not isinstance(data, dict):
            raise ValueError('Payload must be a JSON object, not a list or scalar.')
        return data

    def _extract_standard_payload(self, payload: dict) -> dict:
        """
        Extract and validate all fields from the standard Integration Service payload.
        Raises ValueError with a descriptive message for any validation failure.
        """
        # ── Required fields ────────────────────────────────────────────────
        for key in REQUIRED_FIELDS:
            if not payload.get(key) and payload.get(key) != 0:
                raise ValueError(f'Required field "{key}" is missing or empty.')

        external_order_id = str(payload['external_order_id']).strip()

        # ── Line items ─────────────────────────────────────────────────────
        items_raw = payload['items']
        if not isinstance(items_raw, list) or len(items_raw) == 0:
            raise ValueError(f'Order {external_order_id}: "items" must be a non-empty list.')

        items = []
        for i, item in enumerate(items_raw):
            if not isinstance(item, dict):
                raise ValueError(f'Order {external_order_id}: item #{i} must be a JSON object.')
            sku = item.get('external_sku', '').strip()
            if not sku:
                raise ValueError(f'Order {external_order_id}: item #{i} is missing "external_sku".')
            qty = float(item.get('quantity', 0))
            if qty <= 0:
                raise ValueError(f'Order {external_order_id}: item "{sku}" has invalid quantity {qty}.')
            items.append({
                'external_sku': sku,
                'product_name': str(item.get('product_name', '')).strip(),
                'quantity':     qty,
                'unit_price':   float(item.get('unit_price', 0.0)),
            })

        # ── Optional / defaulted fields ────────────────────────────────────
        order_date = self._parse_iso_datetime(
            payload.get('order_date'), external_order_id
        )
        declared_total = float(payload.get('total_amount', 0.0))

        # Warn when declared total_amount doesn't match computed item sum
        # (allows up to 1 unit tolerance for rounding / discount differences)
        computed_total = sum(
            float(item.get('quantity', 0)) * float(item.get('unit_price', 0.0))
            for item in items_raw
        )
        if declared_total > 0 and abs(declared_total - computed_total) > 1.0:
            _logger.warning(
                'mc.raw.order: order %s declared total_amount=%.2f but '
                'item sum=%.2f (diff=%.2f). Storing declared value.',
                external_order_id, declared_total, computed_total,
                abs(declared_total - computed_total),
            )

        return {
            'external_order_id': external_order_id,
            'customer_name':     str(payload.get('customer_name', '')).strip(),
            'customer_phone':    str(payload.get('customer_phone', '')).strip(),
            'shipping_address':  str(payload.get('shipping_address', '')).strip(),
            'order_date':        order_date,
            'total_amount':      declared_total,
            'currency':          str(payload.get('currency', 'VND')).strip(),
            'items':             items,
        }

    @staticmethod
    def _parse_iso_datetime(raw, order_id: str) -> str:
        """
        Parse an ISO 8601 datetime string into Odoo's expected format.
        Falls back to now() on missing or invalid input and logs a warning.
        """
        if not raw:
            return fields.Datetime.now()
        try:
            clean = str(raw).replace('Z', '').strip()
            dt = datetime.fromisoformat(clean)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            _logger.warning(
                'mc.raw.order: order %s has invalid order_date %r, defaulting to now()',
                order_id, raw,
            )
            return fields.Datetime.now()

    # ═════════════════════════════════════════════════════════════════════════
    # Processing — converts a parsed raw order into a normalized mc.order
    # ═════════════════════════════════════════════════════════════════════════

    def _process_raw_order(self) -> None:
        """
        Create an mc.order from this parsed raw order.

        On success: sets state='processed', links order_id, logs info entry.
        On failure: sets state='error', writes error_message, logs error entry.

        Safe to call only on state='parsed'. Idempotent: the SQL unique constraint
        on mc.order (channel_id, external_order_id) prevents duplicate orders if
        called twice on the same raw order.
        """
        self.ensure_one()
        if self.state != 'parsed':
            raise UserError(f'Raw order #{self.id} must be in state "parsed" to process.')

        try:
            order = self.env['mc.order']._create_from_raw(self)
            self.write({
                'state':        'processed',
                'error_message': False,
                'processed_at': fields.Datetime.now(),
                'order_id':     order.id,
            })
            self.env['mc.sync.log'].sudo().create({
                'channel_id': self.channel_id.id,
                'log_type':   'info',
                'message':    f'Order {order.name} created from raw order {self.parsed_external_order_id}.',
                'reference':  self.parsed_external_order_id,
            })
        except Exception as exc:
            error_msg = str(exc)
            self.write({'state': 'error', 'error_message': error_msg})
            self.env['mc.sync.log'].sudo().create({
                'channel_id': self.channel_id.id,
                'log_type':   'error',
                'message':    f'Processing failed for raw order #{self.id}: {error_msg}',
                'reference':  self.parsed_external_order_id or f'raw#{self.id}',
            })
            _logger.warning('mc.raw.order._process_raw_order failed id=%s: %s', self.id, error_msg)
