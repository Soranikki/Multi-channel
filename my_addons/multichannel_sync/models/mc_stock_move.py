# -*- coding: utf-8 -*-
from odoo import fields, models


class McStockMove(models.Model):
    """
    Append-only log of every inventory movement.

    Every change to mc.product.stock_qty goes through here:
        out         → stock deducted (order confirmed)
        in          → stock added (cancellation, manual receipt)
        adjustment  → manual stock correction (wizard)

    Never deleted — provides a complete audit trail of inventory history.
    """
    _name = 'mc.stock.move'
    _description = 'Stock Move'
    _order = 'move_date desc, id desc'

    product_id = fields.Many2one(
        comodel_name='mc.product',
        string='Product',
        required=True,
        ondelete='restrict',
        index=True,
    )
    move_type = fields.Selection(
        selection=[
            ('in',         'Stock In'),
            ('out',        'Stock Out'),
            ('adjustment', 'Adjustment'),
        ],
        string='Move Type',
        required=True,
        index=True,
    )
    quantity = fields.Float(
        string='Quantity',
        digits=(12, 3),
        required=True,
    )
    reference = fields.Char(
        string='Reference',
        help='Order name or other reference that triggered this movement.',
        index=True,
    )
    channel_id = fields.Many2one(
        comodel_name='mc.channel',
        string='Channel',
        ondelete='set null',
    )
    note = fields.Char(string='Note')
    move_date = fields.Datetime(
        string='Move Date',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        index=True,
    )

    # Convenience computed field: balance sign
    signed_quantity = fields.Float(
        string='Signed Quantity',
        compute='_compute_signed_quantity',
        store=True,
        digits=(12, 3),
        help='Positive for in/adjustment-positive, negative for out.',
    )

    def _compute_signed_quantity(self) -> None:
        for move in self:
            move.signed_quantity = move.quantity if move.move_type in ('in', 'adjustment') else -move.quantity
