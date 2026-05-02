# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class McStockAdjustmentWizard(models.TransientModel):
    """
    Transient wizard for manual stock adjustments on a product.
    Accessible from the product form via the 'Adjust Stock' button.

    Creates an mc.stock.move (type=adjustment) and updates mc.product stock_qty.
    """
    _name = 'mc.stock.adjustment.wizard'
    _description = 'Stock Adjustment Wizard'

    product_id = fields.Many2one(
        comodel_name='mc.product',
        string='Product',
        required=True,
        readonly=True,
    )
    current_stock = fields.Float(
        string='Current Stock',
        digits=(12, 3),
        readonly=True,
    )
    adjustment_type = fields.Selection(
        selection=[
            ('add',    'Add Stock (Incoming)'),
            ('remove', 'Remove Stock (Write-off / Correction)'),
        ],
        string='Adjustment Type',
        required=True,
        default='add',
    )
    quantity = fields.Float(
        string='Quantity',
        digits=(12, 3),
        required=True,
        default=1.0,
    )
    reason = fields.Char(
        string='Reason',
        required=True,
        help='Brief explanation for this stock adjustment (e.g. "Physical count correction", "Damaged goods write-off").',
    )

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self) -> None:
        if self.product_id:
            self.current_stock = self.product_id.stock_qty

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('quantity')
    def _check_quantity_positive(self) -> None:
        for wizard in self:
            if wizard.quantity <= 0:
                raise ValidationError('Quantity must be greater than zero.')

    # ── Action ────────────────────────────────────────────────────────────────

    def action_apply(self):
        """
        Apply the stock adjustment:
        - Adds or subtracts from product.stock_qty.
        - Creates an mc.stock.move with type='adjustment'.
        - Blocks if a remove would drive stock below zero.
        """
        self.ensure_one()
        product = self.product_id

        if self.adjustment_type == 'remove':
            new_stock = product.stock_qty - self.quantity
            if new_stock < 0:
                raise UserError(
                    f'Cannot remove {self.quantity} units from "{product.name}": '
                    f'only {product.stock_qty} in stock (would go negative).'
                )
            product.write({'stock_qty': new_stock})
            move_type = 'adjustment_out'
            note = f'Manual removal — {self.reason}'
        else:
            product.write({'stock_qty': product.stock_qty + self.quantity})
            move_type = 'adjustment_in'
            note = f'Manual addition — {self.reason}'

        self.env['mc.stock.move'].create({
            'product_id': product.id,
            'move_type':  move_type,
            'quantity':   self.quantity,
            'reference':  f'ADJ/{product.internal_sku}',
            'note':       note,
        })

        return {'type': 'ir.actions.act_window_close'}
