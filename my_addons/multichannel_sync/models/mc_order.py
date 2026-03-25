# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class McOrder(models.Model):
    """
    Normalized processed order — the Single Source of Truth for all orders
    that have passed through the data pipeline.

    Created exclusively by _process_raw_order() on mc.raw.order.
    Never created manually (except for testing).

    State machine:
        draft      → Order created from pipeline, stock reserved.
                     Awaiting confirmation.
        confirmed  → Stock deducted, order locked.
        done       → Fulfilled / shipped.
        cancelled  → Cancelled. Stock restored if was confirmed.
    """
    _name = 'mc.order'
    _description = 'Multichannel Order'
    _order = 'order_date desc, name desc'
    _inherit = ['mail.thread']

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Order Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
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
        readonly=True,
        help='Original order ID from the source platform.',
    )
    raw_order_id = fields.Many2one(
        comodel_name='mc.raw.order',
        string='Source Raw Order',
        readonly=True,
        ondelete='set null',
    )

    # ── Customer info ─────────────────────────────────────────────────────────

    customer_name     = fields.Char(string='Customer Name')
    customer_phone    = fields.Char(string='Customer Phone')
    customer_email    = fields.Char(string='Customer Email')
    shipping_address  = fields.Char(string='Shipping Address')

    # ── Dates ─────────────────────────────────────────────────────────────────

    order_date = fields.Datetime(
        string='Order Date',
        default=fields.Datetime.now,
        index=True,
    )

    # ── State machine ─────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('confirmed', 'Confirmed'),
            ('done',      'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='draft',
        required=True,
        index=True,
        tracking=True,
    )

    # ── Financials ────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    total_amount = fields.Float(
        string='Total Amount',
        digits=(12, 2),
        compute='_compute_total_amount',
        store=True,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────

    line_ids = fields.One2many(
        comodel_name='mc.order.line',
        inverse_name='order_id',
        string='Order Lines',
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Text(string='Notes')

    # ── SQL constraints (idempotency) ─────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_channel_external_order',
            'UNIQUE(channel_id, external_order_id)',
            'An order with this external order ID already exists for this channel.',
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # Computed fields
    # ═════════════════════════════════════════════════════════════════════════

    @api.depends('line_ids.subtotal')
    def _compute_total_amount(self) -> None:
        for order in self:
            order.total_amount = sum(order.line_ids.mapped('subtotal'))

    # ═════════════════════════════════════════════════════════════════════════
    # Sequence
    # ═════════════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('mc.order') or 'New'
        return super().create(vals_list)

    def action_open_raw_order(self) -> dict:
        """Navigate back to the source raw order."""
        self.ensure_one()
        if not self.raw_order_id:
            raise UserError('No source raw order linked to this order.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Raw Order',
            'res_model': 'mc.raw.order',
            'view_mode': 'form',
            'res_id': self.raw_order_id.id,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # State transition actions (UI buttons)
    # ═════════════════════════════════════════════════════════════════════════

    def action_confirm(self):
        """
        Confirm a draft order.
        - Checks available stock for every line.
        - Deducts stock_qty and releases reserved_qty.
        - Creates mc.stock.move records (type=out) per line.
        - Sets state = 'confirmed'.
        Blocks with UserError if any product is insufficiently stocked.
        """
        for order in self.filtered(lambda o: o.state == 'draft'):
            order._check_stock_availability()
            order._deduct_stock()
            order.write({'state': 'confirmed'})
            order.message_post(body='Order confirmed. Stock deducted.')

    def action_mark_done(self):
        """Mark a confirmed order as done/fulfilled."""
        for order in self.filtered(lambda o: o.state == 'confirmed'):
            order.write({'state': 'done'})
            order.message_post(body='Order marked as done.')

    def action_cancel(self):
        """
        Cancel an order.
        - If confirmed: restores stock and creates reversal mc.stock.move records.
        - If draft: releases stock reservation only.
        """
        for order in self.filtered(lambda o: o.state in ('draft', 'confirmed')):
            if order.state == 'confirmed':
                order._restore_stock()
                order.message_post(body='Order cancelled. Stock restored.')
            elif order.state == 'draft':
                order._release_reservation()
                order.message_post(body='Draft order cancelled. Reservation released.')
            order.write({'state': 'cancelled'})

    # ═════════════════════════════════════════════════════════════════════════
    # Stock logic (called by action_confirm / action_cancel)
    # Detailed implementation lives in Phase 4 — stubs here keep Phase 3
    # fully installable while Phase 4 fills in the body.
    # ═════════════════════════════════════════════════════════════════════════

    def _check_stock_availability(self) -> None:
        """
        Raise UserError if any order line requests more than available_qty.
        Lists ALL blocking products in one error so the user can fix them at once.
        """
        insufficient = []
        for line in self.line_ids:
            product = line.product_id
            if line.quantity > product.available_qty:
                insufficient.append(
                    f'  • {product.name} (SKU: {product.internal_sku}): '
                    f'requested {line.quantity}, available {product.available_qty}'
                )
        if insufficient:
            raise UserError(
                'Cannot confirm order — insufficient stock for:\n' +
                '\n'.join(insufficient)
            )

    def _deduct_stock(self) -> None:
        """
        Deduct stock for each line and log mc.stock.move records.
        Also releases the reservation set when the order was created.
        """
        StockMove = self.env['mc.stock.move']
        for line in self.line_ids:
            product = line.product_id
            # Release reservation, deduct actual stock
            product.write({
                'reserved_qty': max(0.0, product.reserved_qty - line.quantity),
                'stock_qty':    product.stock_qty - line.quantity,
            })
            StockMove.create({
                'product_id': product.id,
                'move_type':  'out',
                'quantity':   line.quantity,
                'reference':  self.name,
                'channel_id': self.channel_id.id,
                'note':       f'Stock deducted on order confirmation: {self.name}',
            })

    def _restore_stock(self) -> None:
        """Restore stock for all lines on cancellation of a confirmed order."""
        StockMove = self.env['mc.stock.move']
        for line in self.line_ids:
            product = line.product_id
            product.write({'stock_qty': product.stock_qty + line.quantity})
            StockMove.create({
                'product_id': product.id,
                'move_type':  'in',
                'quantity':   line.quantity,
                'reference':  self.name,
                'channel_id': self.channel_id.id,
                'note':       f'Stock restored on order cancellation: {self.name}',
            })

    def _release_reservation(self) -> None:
        """Release reserved_qty for all lines when a draft order is cancelled."""
        for line in self.line_ids:
            product = line.product_id
            product.write({
                'reserved_qty': max(0.0, product.reserved_qty - line.quantity),
            })

    # ═════════════════════════════════════════════════════════════════════════
    # Pipeline entry point — called by mc.raw.order._process_raw_order()
    # ═════════════════════════════════════════════════════════════════════════

    @api.model
    def _create_from_raw(self, raw_order) -> 'McOrder':
        """
        Create a normalized mc.order from a parsed mc.raw.order.
        Resolves all external SKUs to internal products via mc.product.mapping.
        Reserves stock for each line.
        Raises UserError if any SKU cannot be mapped.
        """
        items = json.loads(raw_order.parsed_items_json or '[]')

        # ── Resolve all SKUs first — fail fast before creating anything ────
        resolved_lines = []
        unmapped = []
        for item in items:
            mapping = self.env['mc.product.mapping'].search([
                ('channel_id', '=', raw_order.channel_id.id),
                ('external_sku', '=', item['external_sku']),
                ('is_active', '=', True),
            ], limit=1)
            if not mapping:
                unmapped.append(item['external_sku'])
            else:
                resolved_lines.append((mapping, item))

        if unmapped:
            raise UserError(
                f'Cannot process order {raw_order.parsed_external_order_id} — '
                f'unmapped SKU(s) on channel "{raw_order.channel_id.name}":\n' +
                '\n'.join(f'  • {sku}' for sku in unmapped)
            )

        # ── Create the order ───────────────────────────────────────────────
        order = self.create({
            'channel_id':        raw_order.channel_id.id,
            'external_order_id': raw_order.parsed_external_order_id,
            'raw_order_id':      raw_order.id,
            'customer_name':     raw_order.parsed_customer_name,
            'customer_phone':    raw_order.parsed_customer_phone,
            'shipping_address':  raw_order.parsed_shipping_address,
            'order_date':        raw_order.parsed_order_date,
        })

        # ── Create lines and reserve stock ─────────────────────────────────
        for mapping, item in resolved_lines:
            product = mapping.product_id
            subtotal = item['quantity'] * item['unit_price']
            self.env['mc.order.line'].create({
                'order_id':     order.id,
                'product_id':   product.id,
                'mapping_id':   mapping.id,
                'external_sku': item['external_sku'],
                'product_name': item.get('product_name') or product.name,
                'quantity':     item['quantity'],
                'unit_price':   item['unit_price'],
                'subtotal':     subtotal,
            })
            # Reserve stock for this draft order
            product.write({
                'reserved_qty': product.reserved_qty + item['quantity'],
            })

        return order


class McOrderLine(models.Model):
    """
    One line item within an mc.order.
    Stores both the external SKU (for traceability) and the resolved
    internal product (for inventory and reporting).
    """
    _name = 'mc.order.line'
    _description = 'Order Line'
    _order = 'order_id, id'

    order_id = fields.Many2one(
        comodel_name='mc.order',
        string='Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name='mc.product',
        string='Internal Product',
        required=True,
        ondelete='restrict',
    )
    mapping_id = fields.Many2one(
        comodel_name='mc.product.mapping',
        string='Mapping Used',
        ondelete='set null',
        help='The product mapping record that resolved external_sku to product_id.',
    )

    # ── Platform data (preserved for traceability) ────────────────────────────
    external_sku  = fields.Char(string='External SKU',      readonly=True)
    product_name  = fields.Char(string='Product Name (Platform)')

    # ── Quantities and pricing ────────────────────────────────────────────────
    quantity   = fields.Float(string='Quantity',   digits=(12, 3), required=True)
    unit_price = fields.Float(string='Unit Price', digits=(12, 2))
    discount   = fields.Float(string='Discount %', digits=(5, 2), default=0.0)
    subtotal   = fields.Float(
        string='Subtotal',
        digits=(12, 2),
        compute='_compute_subtotal',
        store=True,
    )

    # ── Convenience related fields ────────────────────────────────────────────
    internal_sku    = fields.Char(related='product_id.internal_sku', string='Internal SKU', readonly=True)
    channel_id      = fields.Many2one(related='order_id.channel_id', string='Channel',     readonly=True, store=True)

    @api.depends('quantity', 'unit_price', 'discount')
    def _compute_subtotal(self) -> None:
        for line in self:
            base = line.quantity * line.unit_price
            line.subtotal = base * (1.0 - line.discount / 100.0)
