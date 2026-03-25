# -*- coding: utf-8 -*-
import json
import logging
import urllib.request
import urllib.error

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import config

_logger = logging.getLogger(__name__)


class McProduct(models.Model):
    """
    Internal product master — the Single Source of Truth for all product data.
    External channel SKUs are mapped to these records via mc.product.mapping.
    Stock fields are managed here; movements are logged in mc.stock.move.
    """
    _name = 'mc.product'
    _description = 'Internal Product'
    _order = 'name'

    name = fields.Char(
        string='Product Name',
        required=True,
    )
    internal_sku = fields.Char(
        string='Internal SKU',
        required=True,
        copy=False,
    )
    description = fields.Text(
        string='Description',
    )
    category = fields.Char(
        string='Category',
    )
    sale_price = fields.Float(
        string='Sale Price',
        digits=(12, 2),
        default=0.0,
    )
    cost_price = fields.Float(
        string='Cost Price',
        digits=(12, 2),
        default=0.0,
    )
    active = fields.Boolean(
        default=True,
    )
    image = fields.Binary(
        string='Product Image',
        attachment=True,
    )

    # ── Inventory fields (Phase 1 scaffold, logic added in Phase 4) ──────────

    stock_qty = fields.Float(
        string='Stock Quantity',
        digits=(12, 3),
        default=0.0,
        help='Current on-hand quantity.',
    )
    reserved_qty = fields.Float(
        string='Reserved Quantity',
        digits=(12, 3),
        default=0.0,
        readonly=True,
        help='Quantity reserved by draft orders pending confirmation.',
    )
    available_qty = fields.Float(
        string='Available Quantity',
        digits=(12, 3),
        compute='_compute_available_qty',
        store=True,
        help='Stock on hand minus reserved quantity.',
    )
    low_stock_threshold = fields.Float(
        string='Low Stock Alert Threshold',
        digits=(12, 3),
        default=5.0,
        help='Alert is shown when available_qty falls at or below this value.',
    )
    is_low_stock = fields.Boolean(
        string='Low Stock',
        compute='_compute_is_low_stock',
        store=True,
    )

    # ── Currency (for monetary widget in views) ───────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # ── Stat counters ─────────────────────────────────────────────────────────

    mapping_count = fields.Integer(
        string='Channel Mappings',
        compute='_compute_mapping_count',
    )
    stock_move_count = fields.Integer(
        string='Stock Moves',
        compute='_compute_stock_move_count',
    )
    pending_order_count = fields.Integer(
        string='Pending Orders',
        compute='_compute_pending_order_count',
    )

    _sql_constraints = [
        ('unique_internal_sku', 'UNIQUE(internal_sku)', 'Internal SKU must be unique across all products.'),
    ]

    # ── Compute methods ───────────────────────────────────────────────────────

    @api.depends('stock_qty', 'reserved_qty')
    def _compute_available_qty(self) -> None:
        for product in self:
            product.available_qty = product.stock_qty - product.reserved_qty

    @api.depends('available_qty', 'low_stock_threshold')
    def _compute_is_low_stock(self) -> None:
        for product in self:
            product.is_low_stock = product.available_qty <= product.low_stock_threshold

    def _compute_mapping_count(self) -> None:
        for product in self:
            product.mapping_count = self.env['mc.product.mapping'].search_count(
                [('product_id', '=', product.id)]
            )

    def _compute_stock_move_count(self) -> None:
        for product in self:
            product.stock_move_count = self.env['mc.stock.move'].search_count(
                [('product_id', '=', product.id)]
            )

    def _compute_pending_order_count(self) -> None:
        for product in self:
            product.pending_order_count = self.env['mc.order.line'].search_count([
                ('product_id', '=', product.id),
                ('order_id.state', '=', 'draft'),
            ])

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('stock_qty', 'reserved_qty')
    def _check_stock_not_negative(self) -> None:
        for product in self:
            if product.stock_qty < 0:
                raise ValidationError(
                    f'Stock quantity for "{product.name}" cannot be negative.'
                )
            if product.reserved_qty < 0:
                raise ValidationError(
                    f'Reserved quantity for "{product.name}" cannot be negative.'
                )

    # ── Button actions ────────────────────────────────────────────────────────

    def action_open_mappings(self):
        """Open product mappings filtered to this product."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Mappings — {self.name}',
            'res_model': 'mc.product.mapping',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }

    def action_open_stock_moves(self):
        """Open stock movements filtered to this product."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Stock Moves — {self.name}',
            'res_model': 'mc.stock.move',
            'view_mode': 'tree',
            'domain': [('product_id', '=', self.id)],
        }

    def action_open_pending_orders(self):
        """Open draft order lines where this product appears."""
        self.ensure_one()
        lines = self.env['mc.order.line'].search([
            ('product_id', '=', self.id),
            ('order_id.state', '=', 'draft'),
        ])
        order_ids = lines.mapped('order_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Pending Orders — {self.name}',
            'res_model': 'mc.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', order_ids)],
        }

    def action_adjust_stock(self):
        """Open the stock adjustment wizard for this product."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjust Stock',
            'res_model': 'mc.stock.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
                'default_current_stock': self.stock_qty,
            },
        }

    # ── Two-way stock sync ────────────────────────────────────────────────────

    def write(self, vals: dict) -> bool:
        """
        Override write to trigger an outbound stock-sync push to the Integration
        Service whenever stock_qty or reserved_qty changes on any product.

        The push is fire-and-forget (non-blocking): a failure is logged as a
        warning in mc.sync.log but does NOT roll back the local write.
        The URL is read from odoo.conf: integration_service_url.
        If the key is empty or absent, the push is silently skipped.
        """
        stock_fields = {'stock_qty', 'reserved_qty'}
        needs_sync = bool(stock_fields & set(vals.keys()))
        result = super().write(vals)
        if needs_sync:
            self._push_stock_sync()
        return result

    def _push_stock_sync(self) -> None:
        """
        POST the current available_qty for each product in self to the
        Integration Service endpoint: POST {base_url}/api/mc/stock-update

        Payload per product:
            {
                "internal_sku": "SKU-001",
                "available_qty": 42.0
            }

        Skipped silently if integration_service_url is not configured.
        Errors are caught, logged to mc.sync.log (type=warning), and do not
        raise — the local inventory change is already committed.
        """
        base_url = (config.get('integration_service_url') or '').rstrip('/')
        if not base_url:
            return  # Not configured — skip silently

        endpoint = f'{base_url}/api/mc/stock-update'
        SyncLog = self.env['mc.sync.log']

        for product in self:
            payload = json.dumps({
                'internal_sku': product.internal_sku,
                'available_qty': product.available_qty,
            }).encode('utf-8')
            req = urllib.request.Request(
                url=endpoint,
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    status = resp.status
                    if status not in (200, 201, 204):
                        raise ValueError(f'Unexpected HTTP {status}')
                    _logger.info(
                        'Stock sync pushed for SKU %s → available_qty=%s',
                        product.internal_sku, product.available_qty,
                    )
            except Exception as exc:
                msg = (
                    f'Stock sync push failed for SKU "{product.internal_sku}": {exc}. '
                    f'Local stock is correct; Integration Service was not updated.'
                )
                _logger.warning(msg)
                SyncLog._log(
                    env=self.env,
                    log_type='warning',
                    message=msg,
                    reference=product.internal_sku,
                )
